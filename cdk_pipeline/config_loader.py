from typing import Dict, Any
import yaml
import os
import glob
from .yaml_handlers import register_yaml_handlers

class ConfigLoader:
    """Handles loading and processing of configuration files.

    This class provides functionality to load YAML configuration files,
    process includes, and handle variable substitutions.

    Attributes:
        config_dir: Directory path containing configuration files.
    """

    def __init__(self, config_dir: str = "configs") -> None:
        """Initialize a ConfigLoader instance.

        Args:
            config_dir: Path to the directory containing configuration files.
                Defaults to "configs".
        """
        self.config_dir = config_dir
        register_yaml_handlers()

    def load_account_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all account configuration files from the config directory.

        This method scans the config directory for YAML files, processes them,
        and handles any include directives found in the configurations.

        Returns:
            Dictionary containing parsed configuration data for each account.
            The keys are the configuration names (without extension) and the
            values are dictionaries containing:
                - config_path: Path to the configuration file
                - full_config: Complete parsed YAML content
                - aws_account: AWS account ID
                - aws_region: AWS region

        Raises:
            yaml.YAMLError: If YAML parsing fails.
            KeyError: If referenced variables are not found.
            FileNotFoundError: If included configuration files are not found.
        """
        account_configs: Dict[str, Dict[str, Any]] = {}
        config_pattern = os.path.join(self.config_dir, "*.yml")
        
        for config_path in glob.glob(config_pattern):
            config_name = os.path.splitext(os.path.basename(config_path))[0]
            yaml_content = self.load_yaml_file(config_path)
            
            # Process includes if present
            if 'include' in yaml_content:
                yaml_content = self._process_includes(yaml_content, os.path.dirname(config_path))
            
            account = yaml_content.get('account', {})
            account_configs[config_name] = {
                'config_path': config_path,
                'full_config': yaml_content,
                'aws_account': account.get('aws_account'),
                'aws_region': account.get('aws_region')
            }

        return account_configs

    def load_yaml_file(self, path: str) -> Dict[str, Any]:
        """Load and parse a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed YAML content as a dictionary.

        Raises:
            yaml.YAMLError: If YAML parsing fails.
            FileNotFoundError: If the file is not found.
        """
        with open(path, 'r') as file:
            return yaml.safe_load(file)

    def _process_includes(self, config: Dict[str, Any], base_path: str) -> Dict[str, Any]:
        """Process include directives in configuration files.
        
        Args:
            config: The configuration dictionary containing includes.
            base_path: Base path for resolving relative paths in includes.
            
        Returns:
            Updated configuration with included resources merged.
            
        Raises:
            FileNotFoundError: If included configuration files are not found.
            KeyError: If referenced variables are not found.
        """
        if 'include' not in config:
            return config

        # Create a copy of the original config to work with
        result = config.copy()
        
        # Initialize resources if not present
        if 'resources' not in result:
            result['resources'] = {}

        # Process each include directive
        for include in config['include']:
            include_path = os.path.join(base_path, include['config'])
            if not os.path.exists(include_path):
                raise FileNotFoundError(f"Included configuration file not found: {include_path}")

            # Load the included configuration
            included_config = self.load_yaml_file(include_path)

            # Validate the included configuration has required sections
            if 'inputs' not in included_config:
                raise ValueError(f"Included configuration {include_path} missing 'inputs' section")
            if 'resources' not in included_config:
                raise ValueError(f"Included configuration {include_path} missing 'resources' section")

            # Convert inputs to a dictionary for easier lookup
            input_vars = {}
            for input_item in include.get('inputs', []):
                if isinstance(input_item, dict):
                    input_vars.update(input_item)
                else:
                    # Handle case where input is just a variable name without value
                    input_vars[input_item] = None

            # Validate all required inputs are provided
            required_inputs = set(included_config['inputs'])
            provided_inputs = set(input_vars.keys())
            missing_inputs = required_inputs - provided_inputs
            if missing_inputs:
                raise ValueError(f"Missing required inputs for {include_path}: {missing_inputs}")

            # Process the included resources with variable substitution
            processed_resources = self._process_resource_variables(included_config['resources'], input_vars)

            # Merge the processed resources into the main configuration
            self._merge_resources(result['resources'], processed_resources)

        return result

    def _process_resource_variables(self, resources: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """Process variables in resource configurations.

        This method recursively processes a resource configuration dictionary,
        resolving any variable references or substitutions using the provided
        variables dictionary.
        
        Args:
            resources: Resource configuration dictionary to process.
            variables: Dictionary of variable names and their values.
            
        Returns:
            Processed resource configuration with variables resolved.
        """
        def process_value(value: Any) -> Any:
            if hasattr(value, 'resolve'):
                return value.resolve(variables)
            elif isinstance(value, dict):
                return {k: process_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [process_value(item) for item in value]
            return value

        return process_value(resources)

    def _merge_resources(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Merge source resources into target resources.

        This method performs a deep merge of two resource dictionaries. For lists,
        it extends the target list with source items. For dictionaries, it
        recursively merges them. For other types, it overwrites the target value
        with the source value.
        
        Args:
            target: Target resource dictionary to merge into.
            source: Source resource dictionary to merge from.
        """
        for key, value in source.items():
            if key not in target:
                target[key] = value
            elif isinstance(target[key], list) and isinstance(value, list):
                target[key].extend(value)
            elif isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_resources(target[key], value)
            else:
                target[key] = value
                