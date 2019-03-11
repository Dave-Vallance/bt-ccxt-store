import os
from pathlib import Path

ROOT_PATH = os.path.abspath(Path(os.path.dirname(__file__)).parent)
MAPPING_PATH = os.path.join(ROOT_PATH, 'ccxtbt/resources/broker_mappings.json')
