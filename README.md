# CDK Pipeline

A Python package for initializing and managing private CDK pipelines.

## Installation

This package is hosted in a private pip repository. To install, ensure you have access to the repository and install using:

```bash
pip install git+https://github.com/Ideal-Data-Management/cdk-pipeline.git@master
```

## Requirements

- Python 3.7+
- AWS CDK v2
- Required packages:
  - aws-cdk-lib
  - pyyaml
  - constructs (>=10.0.0,<11.0.0)

## Usage

[Documentation link - TBD]

## Development

### Setting up the development environment

1. Clone the repository:

```bash
git clone https://github.com/Ideal-Data-Management/cdk-pipeline.git
cd cdk-pipeline
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Running Tests

```bash
pytest
```

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.
