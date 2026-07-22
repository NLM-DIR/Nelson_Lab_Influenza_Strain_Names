import logging.config
import yaml
from pathlib import Path
from importlib.resources import files

logger_config_file = files("strain_generator.config").joinpath("logging_config.yaml")
package_config_file = files("strain_generator.config").joinpath("package.yaml")

with open(logger_config_file, "r") as log_f, \
     open(package_config_file, "r") as package_f:
    logger_config = yaml.safe_load(log_f.read())
    package_config = yaml.safe_load(package_f)

# ensure the log file's directory exists before configuring handlers
log_file = logger_config["handlers"]["file"]["filename"]
Path(log_file).parent.mkdir(parents=True, exist_ok=True)

logging.config.dictConfig(logger_config)

logger = logging.getLogger(__name__)