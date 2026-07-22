import logging
import yaml
from importlib.resources import files

# still load package config from YAML
package_config_file = files("strain_generator.config").joinpath("package.yaml")
with open(package_config_file, "r") as package_f:
    package_config = yaml.safe_load(package_f)

# override logging: send everything to stdout, no file handler
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)