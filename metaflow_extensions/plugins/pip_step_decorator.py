"""Implements a step decorator to install libraries via. `pip`.

Implementation notes:
- StepDecorator.task_pre_step runs just before a step begins executing in the
  tasktime environment (not the runtime environment) - e.g. the function will
  run on batch, not on the machine orchestrating the batch run.
- StepDecorator.task_post_step and StepDecorators.task_exception delete the
  `conda.dependencies` file for the flow in the local `.metaflow` store, this
  ensures that subsequent steps that use the same conda environment are not
  polluted by this decorator
"""
import sys
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict, List

from metaflow.decorators import StepDecorator
from metaflow.exception import MetaflowException
from metaflow.flowspec import FlowSpec
from metaflow.graph import FlowGraph
from metaflow.plugins.conda.conda_step_decorator import CondaStepDecorator

from metaflow_extensions.utils import (
    is_mflow_conda_environment,
    is_task_local,
    pip,
    pip_install,
)


class PipStepDecorator(StepDecorator):
    """Step decorator to install libraries via. `pip`.

    To use, add this decorator to your step:
    ```python
    @pip(path="requirements.txt")
    @step
    def MyStep(self):
        ...

    @pip(libraries={"tqdm": ">1.0.1"})
    @step
    def MyNextStep(self):
        ...
    ```

    Parameters:
        path (Path): Relative path (compared to flow file) to `requirements.txt`
          formatted file.
        libraries (dict): Keys are pypi packages, values are versions (or
          version constraints).
    """

    name = "pip"

    defaults = {"path": None, "libraries": None}

    def task_pre_step(
        self,
        step_name,
        task_datastore,
        metadata,
        run_id,
        task_id,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
        ubf_context,
        inputs,
    ):
        """Install packages with pip."""
        flow_dir = Path(sys.argv[0]).parent
        path = (flow_dir / self.attributes["path"]) if self.attributes["path"] else None
        libraries = self.attributes["libraries"]
        path_mode = path is not None
        library_mode = libraries is not None

        if not (path_mode or library_mode):
            raise MetaflowException(
                "The @pip decorator should be specified with exactly one of the"
                "following arguments: {path, libraries}"
            )

        if path_mode:
            pip_install_reqs(path)

        if library_mode:
            pip_install_libraries(libraries)

    def task_post_step(
        self, step_name, flow, graph, retry_count, max_user_code_retries
    ):
        """After step has run, ensure local conda environment is fresh."""
        ensure_conda_integrity(step_name, flow, graph)
        return

    def task_exception(
        self, exception, step_name, flow, graph, retry_count, max_user_code_retries
    ):
        """After step exception, ensure local conda environment is fresh."""
        ensure_conda_integrity(step_name, flow, graph)
        return


def ensure_conda_integrity(step_name: str, flow: FlowSpec, graph: FlowGraph) -> None:
    """If using conda and local runtime, ensure subsequent steps get clean env."""
    if is_task_local() and is_mflow_conda_environment():
        step_decorators = graph.nodes[step_name].decorators
        # Triggers re-creation of Conda env after extra installation actions
        # has possibly 'polluted' it.
        clear_local_conda_cache(flow.name, step_decorators)
    return


def clear_local_conda_cache(
    flow_name: str, step_decorators: List[StepDecorator]
) -> None:
    """Clear `.metaflow/{flow_name}/conda.dependencies`."""
    conda_decorator = next(
        d for d in step_decorators if isinstance(d, CondaStepDecorator)
    )  # There can be only one Conda decorator per step

    local_root = conda_decorator.local_root  # Local .metaflow folder
    conda_deps_path = Path(local_root) / flow_name / "conda.dependencies"
    # Existence check for robustness, this method could get called multiple times
    # (in post `task_post_step` and `task_exception`) depending on retry behaviour
    if conda_deps_path.exists():
        conda_deps_path.unlink()

    return


# https://www.python.org/dev/peps/pep-0440/#version-specifiers
PKG_CONSTRAINT_OPS = {"==", ">=", "<=", "<", ">", "~=", "!="}


def fill_constraint(pkg_version: str) -> str:
    """Add constraint `pkg_version` if not already prefixed with equality constraint."""
    if not any(pkg_version.startswith(str_op) for str_op in PKG_CONSTRAINT_OPS):
        return "==" + pkg_version
    else:
        return pkg_version


def pip_install_libraries(libraries: Dict[str, str]) -> None:
    """Install `libraries` with `pip`."""
    pip_install(
        sys.executable, tuple(k + fill_constraint(v) for k, v in libraries.items())
    )
    _ensure_consistent_pip_deps()


def _ensure_consistent_pip_deps():
    try:
        pip(sys.executable, "check", capture_output=True)
    except CalledProcessError as exc:
        err_msg = f"""Inconsistent environment when using @pip:
            > {exc.stdout.decode().strip()}
            > Pass `check=False` to ignore this consistency check
            """
        raise MetaflowException(err_msg) from None


def pip_install_reqs(path: Path) -> None:
    """`pip install -r <path>`."""
    pip_install(sys.executable, ("-r", str(path)))
    _ensure_consistent_pip_deps()