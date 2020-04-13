import boto3
import os
import subprocess
import yaml

from dotenv import load_dotenv
from ebssnapshot import metadata
from invoke import task
from os import getenv
from os.path import abspath, dirname, getctime, join
from glob import glob
from sys import version_info

project_dotenv = join(dirname(__file__), '.env')
load_dotenv(project_dotenv)

home_dotenv = os.path.join(getenv('HOME'), '.env')
if os.path.exists(home_dotenv):
    load_dotenv(project_dotenv)

#
# Format vars
#
root = abspath(dirname(__file__))

# Environment variables
AWS_DEFAULT_REGION = getenv('AWS_DEFAULT_REGION', None)
AWS_ACCOUNT_NUMBER = getenv('AWS_ACCOUNT_NUMBER', None)
PYPI_REPO = getenv("PYPI_REPO", None)


#
# Required tasks - All builds must always have these tasks. Or tasks with these names that do the same work.
#
@task
def clean(c):
    """
    Return project to original state
    """
    c.run("python setup.py clean")
    safe_rm_rf(c, ".eggs")
    safe_rm_rf(c, "build")
    safe_rm_rf(c, "dist")
    safe_rm_rf(c, "reports")
    safe_rm_rf(c, "htmlcov")
    safe_rm_rf(c, "*.egg-info")
    safe_rm_rf(c, "ebssnapshot/*.pyc")


@task(aliases=['pip'])
def deps(c):
    """
    Lock packages to a version using pip compile
    """
    if getctime("requirements-setup.in") > getctime("requirements-setup.txt"):
        c.run("pip-compile --output-file=requirements-setup.txt requirements-setup.in")
    if getctime("requirements.in") > getctime("requirements.txt"):
        c.run("pip-compile --output-file=requirements.txt requirements.in")
    c.run("pip install --quiet --requirement requirements-setup.txt")
    c.run("pip install --quiet --requirement requirements.txt")


@task(post=[deps])
def deps_compile(c):
    """
    Update dependency requirements if any
    """

    def touch(fname, times=None):
        with open(fname, 'a'):
            os.utime(fname, times)

    touch("requirements-setup.in")
    touch("requirements.in")


@task(pre=[deps])
def build(c):
    """
    Build package
    """
    # Create python distribution
    c.run("python setup.py sdist")
    c.run("python setup.py bdist_wheel")
    c.run("mkdir -p build/{version}".format(**_vars()))
    c.run("mkdir -p dist")


@task
def build_docker(c, rel=False):
    """
    Build docker image
    """
    cmds = [
        "docker build --tag=sre/{name}_region:{version} --file=Dockerfile.{name} .".format(
            name='create_snapshot',
            **_vars(rel=rel)
        ),
        "docker build --tag=sre/{name}_region:{version} --file=Dockerfile.{name} .".format(
            name='expire_snapshot',
            **_vars(rel=rel)
        ),
        "docker build --tag=sre/{name}:{version} --file=Dockerfile .".format(
            name='ebssnapshot',
            **_vars(rel=rel)
        ),
    ]

    for cmd in cmds:
        c.run(cmd)


@task()
def install(c):
    """
    Install Package(s)
    """
    c.run("pip install -q dist/{project}-{version}*.whl".format(**_vars()))


@task(aliases=['upload'])
def deploy(c, rel=False):
    """
    Upload package to a PyPi server
    """
    if PYPI_REPO:
        c.run(
            "python setup.py sdist bdist_wheel upload -r {PYPI_REPO}".format(**_vars(rel)))
    deploy_docker_registry(c, rel=rel)


def login_docker(c, aws_account_number, region):
    """
    Login to docker
    """
    cmd = (
        "eval $(aws ecr get-login --no-include-email "
        "--registry-ids {aws_account_number} "
        "--region {region})"
    )
    c.run(cmd.format(**locals()))


@task()
def deploy_docker_registry(c, rel=False):
    """
    Upload to docker registry
    """
    fmt_vars = _vars(rel)
    config = docker_registry_config()
    aws_account_number = config['AWS_ACCOUNT_NUMBER']
    version = fmt_vars['version']

    for region in config['AWS_DEFAULT_REGION']:
        login_docker(c, aws_account_number, region)
        for image in config['IMAGES']:
            tag_cmd = (
                "docker tag {image}:{version} "
                "{aws_account_number}.dkr.ecr.{region}.amazonaws.com"
                "{image}:{version}"
            )
            c.run(tag_cmd.format(**locals()))

            push_cmd = (
                "docker push "
                "{aws_account_number}.dkr.ecr.{region}.amazonaws.com"
                "{image}:{version}"
            )
            c.run(push_cmd.format(**locals()))


@task
def test(c):
    """
    Testing
    """
    c.run("pytest")


@task
def version(c):
    """
    Get current version
    """
    print(metadata.__version__)

#
# Utilities
#


def docker_registry_config():
    """
    Docker registry config
    """
    deploy_docker_registry_config = os.environ['DOCKER_REGISTRY_CONFIG']
    with open(deploy_docker_registry_config, 'r') as stream:
        return yaml.load(stream)

    return None


def git_branch():
    """
    Git return current branch
    """
    try:
        cur_branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        return cur_branch.rstrip('\n')
    except subprocess.CalledProcessError:
        return None


def git_has_version(tag):
    """
    :param tag: Tag string
    :rtype: bool
    """
    subprocess.call(['git', 'pull', '--tags'])

    try:
        # Check tag
        subprocess.check_output(['git', 'rev-parse', tag])
        return True
    except subprocess.CalledProcessError:
        return False


def safe_rm_rf(c, pattern):
    """
    Safely delete files
    """
    projdir = abspath(dirname(__file__))
    for f in glob(pattern):
        fullpath = abspath(f)
        if not fullpath.startswith(projdir):
            msg = "File {} is not a project file".format(fullpath)
            raise Exception(msg)

        c.run("rm -rf {}".format(fullpath))


def _vars(rel=False):
    fmt_vars = {
        'PYPI_REPO': PYPI_REPO,
        'project': metadata.__project__,
        'version': metadata.__version__,
        'root': root,
    }
    return fmt_vars
