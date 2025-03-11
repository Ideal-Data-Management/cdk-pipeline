from dataclasses import dataclass
from typing import List, Set, Type, Any, Dict
from aws_cdk import (
    Stack,
    Stage,
    pipelines,
    Environment,
    aws_codebuild as codebuild,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_codestarnotifications as notifications
)
from constructs import Construct
import yaml
import glob
import os

@dataclass
class AbstractPipelineConfig:
    """Configuration class for abstract CDK Pipeline settings.

    Args:
        connection_arn: AWS CodeStar connection ARN for GitHub.
        github_repo: GitHub repository path.
        repo_branch: Git branch to use for deployments. Defaults to "master".
        prod_configs: Set of configuration names considered as production. Defaults to None.
        notification_emails: List of email addresses for pipeline notifications. Defaults to None.
        cdk_version: Version of CDK to use. Defaults to "latest".
        config_dir: Directory containing configuration YAML files. Defaults to "configs".
    """
    connection_arn: str
    github_repo: str
    repo_branch: str = "master"
    prod_configs: Set[str] = None
    notification_emails: List[str] = None
    cdk_version: str = "latest"
    config_dir: str = "configs"


class AbstractPipelineStack(Stack):
    """Abstract base class for CDK Pipeline stacks.

    This class provides a reusable framework for creating multi-account deployment pipelines
    that can work with any stack type and configuration parser.

    Args:
        scope: The scope in which to define this construct.
        id: The scoped construct ID.
        pipeline_config: Configuration settings for the pipeline.
        stack_class: The class of the stack to be deployed.
        stack_config_class: The class used to parse stack configuration.
        **kwargs: Additional keyword arguments to pass to the parent Stack.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        pipeline_config: AbstractPipelineConfig,
        stack_class: Type[Stack],
        stack_config_class: Type[Any],
        **kwargs: Any
    ) -> None:
        super().__init__(scope, id, **kwargs)
        self.pipeline_config = pipeline_config
        self.stack_class = stack_class
        self.stack_config_class = stack_config_class
        
        source = self._create_pipeline_source()
        pipeline = self._create_pipeline(source)
        
        account_configs = self._load_account_configs()
        self._create_waves(pipeline, account_configs)
        pipeline.build_pipeline()
        self._setup_notifications(pipeline)

    def _create_pipeline_source(self) -> pipelines.CodePipelineSource:
        """Creates and returns the pipeline source configuration.

        Returns:
            A CodePipelineSource object configured with GitHub connection details.
        """
        return pipelines.CodePipelineSource.connection(
            self.pipeline_config.github_repo,
            self.pipeline_config.repo_branch,
            connection_arn=self.pipeline_config.connection_arn
        )

    def _create_pipeline(self, source: pipelines.CodePipelineSource) -> pipelines.CodePipeline:
        """Creates the main pipeline with synth step.

        Args:
            source: The source configuration for the pipeline.

        Returns:
            A configured CodePipeline object.
        """
        return pipelines.CodePipeline(
            self,
            "Pipeline",
            cross_account_keys=True,
            code_build_defaults=pipelines.CodeBuildOptions(
                build_environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5
                )
            ),
            synth=pipelines.ShellStep(
                "Synth",
                input=source,
                install_commands=[
                    "pip install --upgrade pip",
                    "pip install -r requirements.txt",
                    "npm uninstall -g aws-cdk",
                    f"npm install -g aws-cdk@{self.pipeline_config.cdk_version}"
                ],
                commands=["cdk synth"]
            )
        )

    def _load_account_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all account configuration files from the config directory.

        Returns:
            Dictionary containing parsed configuration data for each account.

        Raises:
            yaml.YAMLError: If YAML parsing fails.
        """
        account_configs: Dict[str, Dict[str, Any]] = {}
        config_pattern = os.path.join(self.pipeline_config.config_dir, "*.yml")
        
        for config_path in glob.glob(config_pattern):
            config_name = os.path.splitext(os.path.basename(config_path))[0]
            with open(config_path, 'r') as file:
                yaml_content = yaml.safe_load(file)
                account = yaml_content.get('account', {})
                account_configs[config_name] = {
                    'config_path': config_path,
                    'full_config': yaml_content,
                    'aws_account': account.get('aws_account'),
                    'aws_region': account.get('aws_region')
                }

        return account_configs

    def _create_stage_instance(self, config_name: str, config_path: str, **kwargs: Any) -> Stage:
        """Create a new stage instance with the specified configuration.

        Args:
            config_name: Name of the configuration to use.
            config_path: Path to the configuration file.
            **kwargs: Additional keyword arguments for stage creation.

        Returns:
            A configured Stage instance.

        Raises:
            ValueError: If there's an error in configuration parsing.
            RuntimeError: If there's an unexpected error during stage creation.
        """
        class DeploymentStage(Stage):
            def __init__(self_stage: Stage, scope: Construct, id: str, **kwargs: Any) -> None:
                super().__init__(scope, id, **kwargs)

                with open(config_path, 'r') as file:
                    yaml_content = yaml.safe_load(file)
                    account_info = yaml_content.get('account', {})

                config = self.stack_config_class(yaml_content)
                self.stack_class(
                    self_stage,
                    str(self.stack_class.__name__),
                    config,
                    env=Environment(
                        account=account_info.get('aws_account'),
                        region=account_info.get('aws_region')
                    )
                )

        return DeploymentStage(self, config_name, **kwargs)

    def _create_waves(
        self,
        pipeline: pipelines.CodePipeline,
        account_configs: Dict[str, Dict[str, Any]]
    ) -> None:
        """Create deployment waves based on production vs non-production configs.
        Args:
            pipeline: The pipeline to add waves to.
            account_configs: Dictionary of account configurations.
        """
        dev_stages: List[tuple[str, str]] = []
        prod_stages: List[tuple[str, str]] = []

        for config_name in account_configs:
            config_path = f"{self.pipeline_config.config_dir}/{config_name}.yml"
            if self.pipeline_config.prod_configs and config_name in self.pipeline_config.prod_configs:
                prod_stages.append((config_name, config_path))
            else:
                dev_stages.append((config_name, config_path))

        if dev_stages:
            dev_wave = pipeline.add_wave("DevelopmentDeployments")
            for config_name, config_path in dev_stages:
                dev_wave.add_stage(self._create_stage_instance(config_name.capitalize(), config_path))

        if prod_stages:
            approval_wave = pipeline.add_wave("ProductionApproval")
            approval_wave.add_post(
                pipelines.ManualApprovalStep(
                    "PromoteToProd",
                    comment="Please review the development deployment and approve to proceed to production environments"
                )
            )

            # Add production wave
            prod_wave = pipeline.add_wave("ProductionDeployments")
            for config_name, config_path in prod_stages:
                prod_wave.add_stage(
                    self._create_stage_instance(config_name.capitalize(), config_path)
                )

    def _setup_notifications(self, pipeline: pipelines.CodePipeline) -> None:
        """Set up pipeline notifications for the provided email addresses.

        Args:
            pipeline: The pipeline to set up notifications for.
        """
        if not self.pipeline_config.notification_emails:
            return

        topic = sns.Topic(self, "PipelineNotificationsTopic")
        
        topic.add_subscription(
            *[subscriptions.EmailSubscription(email) 
              for email in self.pipeline_config.notification_emails]
        )
        
        notifications.NotificationRule(
            self,
            f"{self.stack_class.__name__}PipelineNotificationRule",
            source=pipeline.pipeline,
            events=[
                "codepipeline-pipeline-pipeline-execution-succeeded",
                "codepipeline-pipeline-pipeline-execution-failed",
                "codepipeline-pipeline-manual-approval-needed"
            ],
            targets=[topic]
        )
