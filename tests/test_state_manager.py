import json
import os
import subprocess
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from openmaskit_companion import manager
from openmaskit_companion.state import Profile, identifier, local_endpoint, read_json, write_json


@pytest.mark.parametrize("value", ["../escape", "UPPER", "space name", "", "a" * 49, ";touch"])
def test_identifiers(value):
    with pytest.raises(ValueError):
        identifier(value)


@pytest.mark.parametrize("url", ["http://evil.test:9495", "https://127.0.0.1:9495", "http://user@localhost:9",
    "http://localhost:9/path", "http://localhost:9?secret=1", "http://localhost", "http://localhost:0",
    "http://localhost:9#fragment", "http://127.0.0.1.evil.test:9", "http://localhost:9\n"])
def test_endpoints_are_loopback_only(url):
    with pytest.raises(ValueError):
        local_endpoint(url)


def test_private_atomic_files(tmp_path):
    path = tmp_path / "state/config.json"
    write_json(path, {"secret": "synthetic"})
    assert read_json(path) == {"secret": "synthetic"}
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        path.chmod(0o644)
        with pytest.raises(ValueError):
            read_json(path)


def test_local_profile_rejects_remote_command_and_extra_fields():
    with pytest.raises(ValidationError):
        Profile(name="Test", command="python")
    with pytest.raises(ValidationError):
        Profile(name="Test", command="/bin/echo", shell=True)


def test_initialize_and_scoped_lifecycle(tmp_path):
    image = manager.IMAGE_PREFIX + "a" * 64
    manager.initialize(tmp_path, image)
    assert "9493" in (tmp_path / "stack/compose.yaml").read_text()
    settings = read_json(tmp_path / "stack/relay/relay.json")
    assert settings["admin_token"] != settings["proxy_token"]
    with pytest.raises(ValueError):
        manager.initialize(tmp_path, image)
    with patch.object(manager, "docker_binary", return_value="/usr/local/bin/docker"), patch.object(subprocess, "run") as run:
        run.side_effect = [subprocess.CompletedProcess([], 0, '"unix:///synthetic/docker.sock"', ""),
                           subprocess.CompletedProcess([], 0, "[]", "")]
        manager.compose(tmp_path, "stop", "--timeout", "45")
        args = run.call_args.args[0]
        assert args[:4] == ["/usr/local/bin/docker", "compose", "--project-name", "openmaskit-companion"]
        assert args[-3:] == ["stop", "--timeout", "45"]
        assert "shell" not in run.call_args.kwargs
        assert "admin_token" not in json.dumps(args)


@pytest.mark.parametrize("image", ["evil/image:latest", "ghcr.io/ricardomartins-gravitee/openmaskit-companion:latest",
    manager.IMAGE_PREFIX + "a" * 63, manager.IMAGE_PREFIX + "g" * 64])
def test_only_immutable_expected_images(image):
    with pytest.raises(ValueError):
        manager.image_digest(image)


def test_unmanaged_directory_cannot_run_docker(tmp_path):
    with patch.object(subprocess, "run") as run, pytest.raises(ValueError):
        manager.compose(tmp_path, "stop")
    run.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ssh://remote.example", "tcp://127.0.0.1:2375", "tcp://remote.example:2376"])
def test_remote_docker_not_managed(endpoint):
    with pytest.raises(ValueError):
        manager.local_docker("docker", {"DOCKER_HOST": endpoint})


def test_explicit_local_docker_context_takes_precedence_over_docker_host():
    environment = {"DOCKER_CONTEXT": "synthetic-local", "DOCKER_HOST": "tcp://remote.example:2376"}
    with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, '"unix:///synthetic/local-docker.sock"', "")) as run:
        manager.local_docker("/usr/local/bin/docker", environment)
    assert run.call_args.args[0] == ["/usr/local/bin/docker", "context", "inspect",
                                     "synthetic-local", "--format", "{{json .Endpoints.docker.Host}}"]
    assert run.call_args.kwargs["env"] is environment


def test_explicit_remote_docker_context_is_rejected_even_if_docker_host_is_local():
    environment = {"DOCKER_CONTEXT": "synthetic-remote", "DOCKER_HOST": "unix:///synthetic/local.sock"}
    with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, '"ssh://docker.example"', "")):
        with pytest.raises(ValueError, match="local Docker socket"):
            manager.local_docker("/usr/local/bin/docker", environment)
