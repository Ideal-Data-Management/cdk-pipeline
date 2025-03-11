from dataclasses import dataclass
from typing import List, Set, Type, Any, Dict, Optional
from aws_cdk import (
    Stack,
    Stage,
    pipelines
)
from constructs import Construct
import yaml

@dataclass
class AbstractPipelineConfig:
    """Configuration class for abstract CDK Pipeline settings.

    Attributes:
        notification_emails: List of email addresses for pipeline notifications.
        github_repo: GitHub repository path.
        repo_branch: Git branch to use for deployments.
        connection_arn: AWS CodeStar connection ARN for GitHub.
        prod_configs: Set of configuration names considered as production.
        cdk_version: Version of CDK to use.
        config_dir: Directory containing configuration YAML files.
    """
    connection_arn: str
    github_repo: str
    repo_branch: Optional[str] = "master"
    prod_configs: Optional[Set[str]] = None
    notification_emails: Optional[List[str]] = None
    cdk_version: Optional[str] = "latest"
    config_dir: Optional[str] = "configs"

class AbstractPipelineStack(Stack):
    """Abstract base class for CDK Pipeline stacks.

    This class provides a reusable framework for creating multi-account deployment pipelines
    that can work with any stack type and configuration parser.
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
        """Initialize the abstract CDK Pipeline Stack.

        Args:
            scope: The scope in which to define this construct.
            id: The scoped construct ID.
            pipeline_config: Configuration settings for the pipeline.
            stack_class: The class of the stack to be deployed.
            stack_config_class: The class used to parse stack configuration.
            **kwargs: Additional keyword arguments to pass to the parent Stack.
        """
        super().__init__(scope, id, **kwargs)
        self.pipeline_config = pipeline_config
        self.stack_class = stack_class
        self.stack_config_class = stack_config_class
        
        # Initialize the pipeline
        source = pipelines.CodePipelineSource.connection(
            self.pipeline_config.github_repo,
            self.pipeline_config.repo_branch,
            connection_arn=self.pipeline_config.connection_arn
        )
        
        # Create the pipeline with synth step
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=source,
                commands=[
                    "npm install -g aws-cdk@" + self.pipeline_config.cdk_version,
                    "pip install -r requirements.txt",
                    "cdk synth"
                ]
            )
        )

        # Set up stages based on configuration
        account_configs = self._load_account_configs()
        self._create_waves(pipeline, account_configs)
        self._setup_notifications(pipeline)

    def _load_account_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all account configuration files from the config directory."""
        account_configs = {}
        import glob
        import os
        
        config_pattern = os.path.join(self.pipeline_config.config_dir, "*.yml")
        for config_path in glob.glob(config_pattern):
            config_name = os.path.splitext(os.path.basename(config_path))[0]
            with open(config_path, 'r') as file:
                account_configs[config_name] = yaml.safe_load(file)
        
        return account_configs

    def _create_stage_instance(
        self,
        config_name: str,
        config_path: str,
        **kwargs: Any
    ) -> Stage:
        """Create a new stage instance with the specified configuration."""
        class DeploymentStage(Stage):
            def __init__(self, scope: Construct, id: str, **kwargs: Any) -> None:
                super().__init__(scope, id, **kwargs)
                with open(config_path, 'r') as file:
                    config_dict = yaml.safe_load(file)
                config = self.stack_config_class(config_dict)
                self.stack_class(self, f"{config_name}Stack", config)
                
        return DeploymentStage(self, config_name, **kwargs)

    def _create_waves(
        self,
        pipeline: pipelines.CodePipeline,
        account_configs: Dict[str, Dict[str, Any]]
    ) -> None:
        """Create deployment waves based on production vs non-production configs."""
        dev_stages = []
        prod_stages = []
        
        for config_name, _ in account_configs.items():
            config_path = f"{self.pipeline_config.config_dir}/{config_name}.yml"
            if config_name in self.pipeline_config.prod_configs:
                prod_stages.append((config_name, config_path))
            else:
                dev_stages.append((config_name, config_path))

        # Add development wave
        if dev_stages:
            dev_wave = pipeline.add_wave("Development")
            for config_name, config_path in dev_stages:
                dev_wave.add_stage(self._create_stage_instance(config_name, config_path))

        # Add production wave with approval
        if prod_stages:
            prod_wave = pipeline.add_wave("Production")
            for config_name, config_path in prod_stages:
                prod_wave.add_stage(
                    self._create_stage_instance(config_name, config_path),
                    pre=[pipelines.ManualApprovalStep(
                    "PromoteToProd",
                    comment="Please review the development deployment and approve to proceed to production environments"
                    )]
                )

    def _setup_notifications(self, pipeline: pipelines.CodePipeline) -> None:
        """Set up pipeline notifications for the provided email addresses."""
        from aws_cdk import (
            aws_sns as sns,
            aws_sns_subscriptions as subscriptions,
            aws_codestarnotifications as notifications
        )
        
        topic = sns.Topic(self, "PipelineNotificationsTopic")
        
        for email in self.pipeline_config.notification_emails:
            subscriptions.EmailSubscription(email).bind(topic)
        
        notifications.NotificationRule(
            self,
            "PipelineNotificationRule",
            source=pipeline.pipeline,
            events=[
                "codepipeline-pipeline-pipeline-execution-succeeded",
                "codepipeline-pipeline-pipeline-execution-failed",
                "codepipeline-pipeline-manual-approval-needed"
            ],
            targets=[topic]
        )
