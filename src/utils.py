"""Various utility functions used across the repo."""

from flask import current_app
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests import exceptions
import requests
import os
import docker
import shutil
import json

from subprocess import check_output
from tempfile import TemporaryDirectory
from pathlib import Path
from urllib.parse import urljoin

from f8a_worker.process import Git
from f8a_worker.utils import cwd, peek, parse_gh_repo

COREAPI_SERVER_URL_REST = "http://{host}:{port}".format(
    host=os.environ.get("BAYESIAN_COREAPI_HTTP_SERVICE_HOST", "bayesian-api"),
    port=os.environ.get("BAYESIAN_COREAPI_HTTP_SERVICE_PORT", "5000"))
docker_client = docker.from_env()


def retrieve_image(name):
    try:
        result = docker_client.images.pull(name)
        print('%r' % result)
    except (docker.errors.BuildError, docker.errors.APIError) as e:
        current_app.logger.error(e)
        raise

    return True


def remove_image(name):
    try:
        docker.images.remove(image=name, force=True)
    except docker.errors.APIError as e:
        current_app.logger.error(e)
        raise


def fetch_container_info(name):
    command = 'cat /etc/redhat-release'
    result = {'os': docker_client.containers.run(name, command).decode('utf-8')}
    current_app.logger.info('Container is running on OS %r' % result['os'])

    command = 'docker inspect {image}'.format(image=name)
    data = check_output(command.split()).decode('utf-8')
    j = json.loads(data)
    result['git-url'] = j[0]['Config']['Labels']['git-url']


def get_session_retry(retries=3, backoff_factor=0.2, status_forcelist=(404, 500, 502, 504),
                      session=None):
    """Set HTTP Adapter with retries to session."""
    session = session or requests.Session()
    retry = Retry(total=retries, read=retries, connect=retries,
                  backoff_factor=backoff_factor, status_forcelist=status_forcelist)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    return session


def get_manifest_file_from_git_repo(git_repo_url):
    repo = ""
    with TemporaryDirectory() as workdir:
        try:
            repo = Git.clone(url=git_repo_url, path="/tmp/")
        except Exception as e:
            print ("Exception %r" % e)
            raise

        with cwd(repo.repo_path):
            if peek(Path.cwd().glob("pom.xml")):
                print ('{}/pom.xml'.format(Path.cwd()))
                f = open('{}/pom.xml'.format(Path.cwd()))
                return f
    return None


class GithubRead:
    """Class with methods to read information about the package from GitHub."""

    # TODO move into its own module
    with TemporaryDirectory() as workdir:
        CLONED_DIR = workdir

    PREFIX_GIT_URL = "https://github.com/"
    PREFIX_URL = "https://api.github.com/repos/"
    RAW_FIRST_URL = "https://raw.githubusercontent.com/"
    MANIFEST_TYPES = ["pom.xml", "package.json", "requirements.txt"]

    def get_manifest_files(self):
        """Retrieve manifest files from cloned repository."""
        manifest_file_paths = []
        for base, dirs, files in os.walk(self.CLONED_DIR):
            if '.git' in dirs:
                dirs.remove('.git')
            if 'node_modules' in dirs:
                dirs.remove('node_modules')
            for filename in files:
                if filename in self.MANIFEST_TYPES:
                    filepath = os.path.join(base, filename)
                    manifest_file_paths.append({
                        "filename": filename,
                        "filepath": filepath
                    })
        return manifest_file_paths

    def get_manifest_details(self, github_url):
        """Retrieve manifest files from cloned repository."""
        manifest_data = []
        supported_manifests = {
            'requirements.txt': True,
            'pom.xml': True,
            'package.json': True
        }
        repo_tuple = parse_gh_repo(github_url)
        if repo_tuple:
            project, repo = repo_tuple.split('/')
        else:
            return None

        last_commit_url = 'https://api.github.com/repos/{project}/{repo}/git/refs/heads/' \
                          'master'.format(project=project, repo=repo)
        trees_url = 'https://api.github.com/repos/{project}/{repo}/git/trees/{sha}?recursive=1'
        raw_content_path = 'https://raw.githubusercontent.com/{project}/{repo}/master/{filename}'

        # Fetch the latest commit of the repo
        try:
            resp = requests.get(last_commit_url)
        except exceptions.RequestException as e:
            print(e)
            return None

        last_commit = ''
        if resp.status_code == 200:
            try:
                last_commit = resp.json()['object']['sha']
            except KeyError as e:
                print(e)
                return None

        # Fetch the contents tree using the last commit sha
        try:
            resp = requests.get(trees_url.format(project=project, repo=repo, sha=last_commit))
        except exceptions.RequestException as e:
            print(e)
            return None

        if resp.status_code == 200:
            try:
                tree = resp.json()['tree']
            except KeyError as e:
                print(e)
                return None

        for t in tree:
            try:
                if supported_manifests[os.path.basename(t['path'])]:
                    manifest_data.append({
                        'filename': os.path.basename(t['path']),
                        'download_url': raw_content_path.format(
                            project=project, repo=repo, filename=t['path']),
                        'filepath': os.path.dirname(t['path'])
                    })
            except KeyError as e:
                print(e)
                continue

        print(manifest_data)
        return manifest_data

    def get_files_github_url(self, github_url):
        """Clone the repository from GitHub and retrieve manifest files from it."""
        manifest_data = []
        repo_suffix = parse_gh_repo(github_url)
        try:
            self.del_temp_files()
            repo_url = urljoin(self.PREFIX_URL, repo_suffix)
            check_valid_repo = requests.get(repo_url)
            if check_valid_repo.status_code == 200:
                repo_clone_url = urljoin(self.PREFIX_GIT_URL, repo_suffix, '.git')
                Git.clone(repo_clone_url, self.CLONED_DIR)
                for file_obj in self.get_manifest_files():
                    file_content = None
                    filename = file_obj.get('filename')
                    filepath = file_obj.get('filepath')
                    with open(filepath, 'rb') as m_file:
                        file_content = m_file.read().decode('utf-8')
                    manifest_data.append({
                        "filename": filename,
                        "content": file_content,
                        "filepath": filepath.replace(self.CLONED_DIR, '')
                    })
        except Exception as e:
            current_app.logger.error("Error in reading repo from github.")
            raise
        finally:
            self.del_temp_files()

        return manifest_data

    def del_temp_files(self):
        """Delete temporary files in the CLONED_DIR repository."""
        if os.path.exists(self.CLONED_DIR):
            shutil.rmtree(self.CLONED_DIR)

