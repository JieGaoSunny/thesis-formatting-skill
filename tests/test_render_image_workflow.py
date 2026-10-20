from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "render-image.yml"
IMAGE = "ghcr.io/jiegaosunny/thesis-formatting-skill-render"


def test_render_image_workflow_publishes_digest_reference() -> None:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert workflow["on"] == {"workflow_dispatch": ""}
    assert workflow["permissions"] == {
        "contents": "read",
        "packages": "write",
    }

    job = workflow["jobs"]["publish"]
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]

    assert steps[0]["uses"] == "actions/checkout@v4"
    assert steps[1]["uses"] == "docker/setup-buildx-action@v3"

    login = steps[2]
    assert login["uses"] == "docker/login-action@v3"
    assert login["with"] == {
        "registry": "ghcr.io",
        "username": "${{ github.actor }}",
        "password": "${{ secrets.GITHUB_TOKEN }}",
    }

    build = steps[3]
    assert build["id"] == "build"
    assert build["uses"] == "docker/build-push-action@v6"
    assert build["with"] == {
        "context": ".",
        "file": "./Dockerfile.render",
        "platforms": "linux/amd64",
        "push": "true",
        "tags": f"{IMAGE}:sha-${{{{ github.sha }}}}",
        "build-args": "SOURCE_COMMIT=${{ github.sha }}\n",
    }

    reference = steps[4]
    assert reference["shell"] == "bash"
    assert (
        f"printf '%s@%s\\n' '{IMAGE}' '${{{{ steps.build.outputs.digest }}}}' "
        "> image-reference.txt"
        in reference["run"]
    )

    upload = steps[5]
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"] == {
        "name": "render-image-reference",
        "path": "image-reference.txt",
    }
