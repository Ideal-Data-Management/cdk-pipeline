from typing import Any, Dict
import yaml

class SubTag:
    """Custom YAML tag handler for !Sub.

    This class implements a custom YAML tag that handles string substitution
    similar to AWS CloudFormation's !Sub function.

    Attributes:
        yaml_tag: The YAML tag identifier for this handler.
        value: The template string containing variables to be substituted.
    """
    yaml_tag = '!Sub'

    def __init__(self, value: str) -> None:
        """Initialize a SubTag instance.

        Args:
            value: The template string containing variables in ${var} format.
        """
        self.value = value

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.Node) -> 'SubTag':
        """Create a SubTag instance from a YAML node.

        Args:
            loader: The YAML loader instance.
            node: The YAML node containing the template string.

        Returns:
            A new SubTag instance initialized with the node's value.
        """
        return cls(node.value)

    def resolve(self, variables: Dict[str, Any]) -> str:
        """Resolve the template string with the provided variables.
        
        Args:
            variables: Dictionary of variable names and their values.
            
        Returns:
            Resolved string with variables replaced.
        """
        result = self.value
        for var_name, var_value in variables.items():
            placeholder = "${" + var_name + "}"
            result = result.replace(placeholder, str(var_value))
        return result

class RefTag:
    """Custom YAML tag handler for !Ref.

    This class implements a custom YAML tag that handles variable references
    similar to AWS CloudFormation's !Ref function.

    Attributes:
        yaml_tag: The YAML tag identifier for this handler.
        value: The name of the variable to be referenced.
    """
    yaml_tag = '!Ref'

    def __init__(self, value: str) -> None:
        """Initialize a RefTag instance.

        Args:
            value: The name of the variable to be referenced, optionally with list index (e.g., "variable[0]").
        """
        # Check if the value contains a list index reference
        if '[' in value and value.endswith(']'):
            var_name, index_str = value.split('[', 1)
            try:
                self.index = int(index_str[:-1])  # Remove the closing bracket and convert to int
                self.value = var_name
                self.is_list_ref = True
            except ValueError:
                # If index is not a valid integer, treat the whole string as a variable name
                self.value = value
                self.is_list_ref = False
        else:
            self.value = value
            self.is_list_ref = False

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.Node) -> 'RefTag':
        """Create a RefTag instance from a YAML node.

        Args:
            loader: The YAML loader instance.
            node: The YAML node containing the variable name.

        Returns:
            A new RefTag instance initialized with the node's value.
        """
        return cls(node.value)

    def resolve(self, variables: Dict[str, Any]) -> Any:
        """Resolve the reference with the provided variables.
        
        Args:
            variables: Dictionary of variable names and their values.
            
        Returns:
            The referenced value. If the reference is to a list element,
            returns the element at the specified index.
            
        Raises:
            KeyError: If the referenced variable is not found.
            IndexError: If the list index is out of range.
            TypeError: If trying to use list indexing on a non-list value.
        """
        if self.value not in variables:
            raise KeyError(f"Referenced variable '{self.value}' not found in inputs")
        
        value = variables[self.value]
        
        if self.is_list_ref:
            if not isinstance(value, (list, tuple)):
                raise TypeError(f"Cannot use list indexing on non-list value: {self.value}")
            try:
                return value[self.index]
            except IndexError:
                raise IndexError(f"List index {self.index} is out of range for variable '{self.value}'")
        
        return value

def register_yaml_handlers() -> None:
    """Register the custom YAML tag handlers.

    This function registers the SubTag and RefTag custom YAML tag handlers with
    the YAML SafeLoader. After registration, the YAML loader will be able to
    process !Sub and !Ref tags in YAML files.
    """
    yaml.SafeLoader.add_constructor(SubTag.yaml_tag, SubTag.from_yaml)
    yaml.SafeLoader.add_constructor(RefTag.yaml_tag, RefTag.from_yaml)
    

