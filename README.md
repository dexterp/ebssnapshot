# EBS Snapshots

## Usage

```
Usage:
    ebssnap create [--readtimeout RTOUT] [--log LEVEL] [--region AWS_REGION] [--workers WORKERS] [--filter FILTER] [--role_arn ROLE]
    ebssnap expire [--readtimeout RTOUT] [--log LEVEL] [--region AWS_REGION] [--workers WORKERS] [--inlife DAYS] [--role_arn ROLE]

Options:
    -h --help                           display help
    --version                           show version
    --inlife DAYS                       Number of days relative to current day where snapshots are considered in life and should NOT be expired [default: -7]
    -r AWS_REGION --region=AWS_REGION   AWS Region. Will default to environment variable AWS_DEFAULT_REGION or the AWS configuration file
    -f FILTER --filter=FILTER           JSON string for filtering volumes
    --readtimeout=RTOUT                 Read timeout in seconds [default: 3600]
    --role_arn=ROLE                     The ARN of the IAM role to Assume. If not specified then will default to using the AWS_ACCESS_KEY and AWS_SECRET_ACCESS_KEY environment variables directly
    --workers=WORKERS                   Number of process/workers [default: 4]
    --log=(INFO|WARN|ERROR)             Log level. [default: WARN]
```

## Installation

```bash
pip install -r requirements-setup.txt
invoke build
invoke install
```

## Development

This project uses [invoke](http://www.pyinvoke.org/) (Similar to Rake/Makefiles).
Tasks are located in the [tasks.py](./tasks.py) python code.

To see the list of available tasks run
```bash
invoke -l
```
```
Available tasks:

  build                    Build package
  build-docker             Build docker image
  clean                    Return project to original state
  deploy (upload)          Upload package to a PyPi server
  deploy-docker-registry   Upload to docker registry
  deploy-lambda            Deploy AWS Lambda
  deps (pip)               Lock packages to a version using pip compile
  deps-compile             Update dependency requirements if any
  install                  Install Package(s)
  release                  Release code
  test                     Testing
  version                  Get current version
```

### Development Work
```bash
# Installs development requirements
pip install -r requirements-setup.txt

invoke clean
invoke build

# Links package for development purposes
pip install -e .
```

## Issues faced while running the script locally

If you are on macOS High Sierra, While running the ebssnap script, you may face the below issue

```bash
objc[18328]: +[__NSPlaceholderDate initialize] may have been in progress in another thread when fork() was called.
objc[18329]: +[__NSPlaceholderDate initialize] may have been in progress in another thread when fork() was called.
objc[18328]: +[__NSPlaceholderDate initialize] may have been in progress in another thread when fork() was called. We cannot safely call it or ignore it in the fork() child process. Crashing instead. Set a breakpoint on objc_initializeAfterForkError to debug.
objc[18329]: +[__NSPlaceholderDate initialize] may have been in progress in another thread when fork() was called. We cannot safely call it or ignore it in the fork() child process. Crashing instead. Set a breakpoint on objc_initializeAfterForkError to debug.
```

## Fix for the issue

Export the below variable and run the script again
```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
```
