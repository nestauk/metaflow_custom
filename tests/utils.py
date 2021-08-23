# type: ignore
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def install_setup_py(setup_path: Path) -> None:
    """Install package (folder with setup.py file) at `setup.path`."""
    pkg_name = subprocess.getoutput(f"{sys.executable} {setup_path}/setup.py --name")
    print(f"Installing `{pkg_name}` for {sys.executable}...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "pip",
            "--upgrade",
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(setup_path),
            "--quiet",
            # Needed to avoid temporary copies of large dirs like `outputs/`
            "--use-feature",
            "in-tree-build",
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )


def remove_pkg(pkg_name: str) -> None:
    """Uninstall `pkg_name`."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "uninstall",
            pkg_name,
            "-y",
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )


@contextmanager
def ch_dir(path: os.PathLike) -> None:
    """Context Manager to change directory to `path`."""
    cwd = os.getcwd()
    os.chdir(path)
    try:
        yield os.getcwd()
    finally:
        os.chdir(cwd)


def run_flow(
    path: os.PathLike,
    datastore: str = "local",
    metadata: str = "local",
    environment: Optional[str] = None,
    batch: bool = False,
    python: str = sys.executable,
) -> None:
    """Run Metaflow at `path`."""
    cmd = [
        python,
        str(path),
        "--datastore",
        str(datastore),
        "--metadata",
        str(metadata),
        "--no-pylint",
    ]

    if batch:
        cmd.extend(["--with", "batch"])

    if environment is not None:
        cmd.extend(["--environment", environment])

    cmd.append("run")

    try:
        out = subprocess.run(cmd, capture_output=True, shell=False, check=True)
    except subprocess.CalledProcessError as e:
        print(e.args)
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        raise e
    return out