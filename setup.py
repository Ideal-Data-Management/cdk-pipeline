from setuptools import setup

setup(
    name='cdk_pipeline',
    version='1.0.0',
    description='Private CDK Pipeline Initalizer',
    url='https://github.com/Ideal-Data-Management/cdk-pipeline.git',
    author='Nathan Stokes',
    author_email='nstokes@idmservices.net',
    license='MIT',
    python_requires='>=3.7',
    packages=['cdk_pipeline'],
    zip_safe=False,
    install_requires=[
        'aws-cdk-lib',
        'pyyaml',
        'constructs>=10.0.0,<11.0.0'
    ]
)