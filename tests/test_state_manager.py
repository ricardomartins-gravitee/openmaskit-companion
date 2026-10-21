import json
import subprocess
from unittest.mock import patch

import pytest
from openmaskit_connector.state import read_json, write_json

from openmaskit_companion import manager


def test_initialize_and_scoped_lifecycle(tmp_path):
    image = manager.IMAGE_PREFIX + "a" * 64
    manager.initialize(tmp_path, image)
    assert "9493" in (tmp_path / "stack/compose.yaml").read_text()
    settings = read_json(tmp_path / "stack/relay/relay.json")
    assert settings["admin_token"] != settings["proxy_token"]
    project = read_json(tmp_path / "stack/managed.json")["project"]
    assert project.startswith(manager.PROJECT + "-")
    assert len(project) == len(manager.PROJECT) + 13
    with pytest.raises(ValueError):
        manager.initialize(tmp_path, image)
    with (
        patch.object(manager, "docker_binary", return_value="/usr/local/bin/docker"),
        patch.object(subprocess, "run") as run,
    ):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, '"unix:///synthetic/docker.sock"', ""),
            subprocess.CompletedProcess([], 0, "[]", ""),
        ]
        manager.compose(tmp_path, "stop", "--timeout", "45")
        args = run.call_args.args[0]
        assert args[:4] == [
            "/usr/local/bin/docker",
            "compose",
            "--project-name",
            project,
        ]
        assert args[-3:] == ["stop", "--timeout", "45"]
        assert "shell" not in run.call_args.kwargs
        assert "admin_token" not in json.dumps(args)


@pytest.mark.parametrize(
    "image",
    [
        "evil/image:latest",
        "ghcr.io/ricardomartins-gravitee/openmaskit-companion:latest",
        manager.IMAGE_PREFIX + "a" * 63,
        manager.IMAGE_PREFIX + "g" * 64,
    ],
)
def test_only_immutable_expected_images(image):
    with pytest.raises(ValueError):
        manager.image_digest(image)


def test_unmanaged_directory_cannot_run_docker(tmp_path):
    with patch.object(subprocess, "run") as run, pytest.raises(ValueError):
        manager.compose(tmp_path, "stop")
    run.assert_not_called()


def test_each_home_gets_a_distinct_compose_project(tmp_path):
    image = manager.IMAGE_PREFIX + "a" * 64
    first, second = tmp_path / "first", tmp_path / "second"
    manager.initialize(first, image)
    manager.initialize(second, image)
    first_project = read_json(first / "stack/managed.json")["project"]
    second_project = read_json(second / "stack/managed.json")["project"]
    assert first_project != second_project
    assert first_project.startswith(manager.PROJECT + "-")
    assert second_project.startswith(manager.PROJECT + "-")


@pytest.mark.parametrize(
    "project",
    [
        "other-project",
        "openmaskit-companion-../../",
        "openmaskit-companion-ABCDEF123456",
    ],
)
def test_untrusted_managed_project_name_is_rejected_before_docker(tmp_path, project):
    image = manager.IMAGE_PREFIX + "a" * 64
    manager.initialize(tmp_path, image)
    marker_path = tmp_path / "stack/managed.json"
    marker = read_json(marker_path)
    marker["project"] = project
    write_json(marker_path, marker)
    with (
        patch.object(manager, "docker_binary") as binary,
        pytest.raises(ValueError, match="companion-managed"),
    ):
        manager.compose(tmp_path, "stop")
    binary.assert_not_called()


@pytest.mark.parametrize(
    "endpoint",
    ["ssh://remote.example", "tcp://127.0.0.1:2375", "tcp://remote.example:2376"],
)
def test_remote_docker_not_managed(endpoint):
    with pytest.raises(ValueError):
        manager.local_docker("docker", {"DOCKER_HOST": endpoint})


def test_explicit_local_docker_context_takes_precedence_over_docker_host():
    environment = {
        "DOCKER_CONTEXT": "synthetic-local",
        "DOCKER_HOST": "tcp://remote.example:2376",
    }
    with patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            [], 0, '"unix:///synthetic/local-docker.sock"', ""
        ),
    ) as run:
        manager.local_docker("/usr/local/bin/docker", environment)
    assert run.call_args.args[0] == [
        "/usr/local/bin/docker",
        "context",
        "inspect",
        "synthetic-local",
        "--format",
        "{{json .Endpoints.docker.Host}}",
    ]
    assert run.call_args.kwargs["env"] is environment


def test_explicit_remote_docker_context_is_rejected_even_if_docker_host_is_local():
    environment = {
        "DOCKER_CONTEXT": "synthetic-remote",
        "DOCKER_HOST": "unix:///synthetic/local.sock",
    }
    with patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, '"ssh://docker.example"', ""),
    ):
        with pytest.raises(ValueError, match="local Docker socket"):
            manager.local_docker("/usr/local/bin/docker", environment)
