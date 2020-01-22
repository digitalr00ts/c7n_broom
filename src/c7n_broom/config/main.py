""" Main of c7n_broom.config """
import dataclasses
import itertools
import logging
import os
import pathlib
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import c7n.config
import yaml
from vyper import Vyper


_LOGGER = logging.getLogger(__name__)


def get_config(filename: str = "config", path: PathLike = Path(".")):
    """ Read in config file """
    # TODO: Figure out why defaults does not work.
    default_path = "global.path"
    defaults = {
        "policies": {"path": path},
        "path": path,
    }
    config = Vyper(filename)
    config.set_default("global", defaults)
    config.add_config_path(Path(path))
    config.read_in_config()
    if not config.is_set(default_path):
        _LOGGER.info("Setting default path to %s", path)
        config.set(default_path, path)
    return config


# TODO: change to factory and do not inherit from c7n's databag
@dataclasses.dataclass()
class C7nConfig(c7n.config.Config):  # pylint: disable=too-many-instance-attributes
    """Configuration for c7n."""

    # FIXME: reading var env here seem to overwrite passed parameter
    #        this maybe due to c7n's "databag"
    profile: str  # = os.environ.get("AWS_PROFILE", "")
    configs: Iterable[str] = dataclasses.field(default_factory=list)
    dryrun: bool = True

    output_dir: str = ""
    regions: Iterable[str] = dataclasses.field(default_factory=set, compare=False)
    metrics: Optional[str] = "aws://master?region=us-east-1"
    policy_filter: Optional[str] = None
    resource_type: Optional[str] = None

    cache_period: int = 15
    cache: Optional[str] = None

    # Report
    format: str = "simple"
    days: float = 1
    no_default_fields: bool = False
    field: List[str] = dataclasses.field(default_factory=list)
    raw: Optional[pathlib.Path] = None

    region: str = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    metrics_enabled: bool = True
    debug: bool = False
    # verbose: bool = True

    account_id: Optional[str] = dataclasses.field(default=None)
    assume_role: Optional[str] = dataclasses.field(default=None)
    external_id: Optional[str] = dataclasses.field(default=None)
    log_group: Optional[str] = dataclasses.field(default=None)
    authorization_file: Optional[str] = dataclasses.field(default=None)
    tracer: str = dataclasses.field(default="default")

    # IDK, but c7n will throw errors w/o it.
    vars: Optional[List] = None

    def __post_init__(self):
        if not self.profile:
            raise TypeError("Profile must be set.")

        for k, v in c7n.config.Config.empty().items():
            if k not in dataclasses.asdict(self).keys():
                _LOGGER.debug("Adding missing attribute %s:%s.", k, v)
                setattr(self, k, v)

        c7n_home = pathlib.Path.home().joinpath(".cache/c7n").joinpath(self.profile)

        self.regions = set(self.regions)

        if self.cache is None:
            self.cache = str(c7n_home.joinpath("cloud-custodian.cache"))

        if self.output_dir == "":
            self.output_dir = str(c7n_home)

        if not self.configs:
            _LOGGER.warning("No configuration files set.")
        else:
            if not self.resource_type:
                self.resource_type = self._get_policy_resource

        _LOGGER.debug("Created config object %s%s", self.profile, self.configs)

    @property
    def _get_policy_resource(self) -> Optional[str]:
        """
        Returns resource type if the resources are the same across the policies in the policy file.
        Otherwise returns None
        """

        policy_resources = set(
            map(lambda policy_item: policy_item.get("resource"), self.get_policy_data())
        )
        rtn = policy_resources.pop() if len(policy_resources) == 1 else None
        if not rtn:
            _LOGGER.warning("%s resource types found.", len(policy_resources))
        return rtn

    @property
    def get_str(self):
        """
        Returns a string for the c7n_config.
        Used for creating files names.
        """
        return ":".join(
            [self.profile, ", ".join(map(lambda policy: Path(policy).stem, self.configs)),]
        )

    def get_config_data(self) -> Iterable[Dict[str, Any]]:
        """ Returns iterable of dict for all files in self.config """

        def get_policy_data(policy_file) -> Dict[str, Any]:
            policy_file = Path(policy_file)
            return yaml.safe_load(policy_file.read_bytes()) if policy_file.is_file() else dict()

        return map(get_policy_data, self.configs)

    def get_policy_data(self) -> Iterable[Dict[str, Any]]:
        """ Returns iterable of policies across all policies in configs """

        def policy_data(data_):
            return data_.get("policies")

        return itertools.chain.from_iterable(
            map(policy_data, filter(policy_data, self.get_config_data()))
        )
