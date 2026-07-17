import logging
import logging.config
import yaml

with open("config/logging_config.yaml", "r") as log_f, \
     open("config/package.yaml", "r") as package_f:

    logger_config = yaml.safe_load(log_f.read())
    logging.config.dictConfig(logger_config)

    package_config = yaml.safe_load(package_f)

logger = logging.getLogger(__name__)
