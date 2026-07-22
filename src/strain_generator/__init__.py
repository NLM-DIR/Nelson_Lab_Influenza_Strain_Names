import logging
import logging.config
import yaml
from importlib.resources import files

logger_config_file = files("strain_generator.config").joinpath("logging_config.yaml")
package_config_file = files("strain_generator.config").joinpath("package.yaml")

with open(logger_config_file, "r") as log_f, \
     open(package_config_file, "r") as package_f:

    logger_config = yaml.safe_load(log_f.read())
    logging.config.dictConfig(logger_config)

    package_config = yaml.safe_load(package_f)

logger = logging.getLogger(__name__)
