import os

import functions_framework
import yaml
from helper import process_files, load_files

@functions_framework.http
def entry_point(request=None):
    # Load configuration from YAML file
    with open("config.yml", 'r') as file:
        config = yaml.safe_load(file)

    # Determine the environment

    asset = "CAPITALIZATIONS"
    csv_files = load_files(config, asset)
    process_files(config, csv_files, asset)

    return "Data insertion successfully completed !\n"

if os.getenv('K_SERVICE') and os.getenv('FUNCTION_TARGET'):
    pass
else:
    print(entry_point())
