from setuptools import setup

setup(
    name='cdk-pipeline',
    version='1.0.0',
    description='Private CDK Pipeline Initalizer',
    url='git@github.com:nstokes-idm/cdk-pipeline.git',
    author='Nathan Stokes',
    author_email='nstokes@idmservices.net',
    license='unlicense',
    packages=['cdk-pipeline'],
    zip_safe=False,
    requires=['aws-cdk-lib', 'pyyaml', 'constructs>=10.0.0,<11.0.0']
)