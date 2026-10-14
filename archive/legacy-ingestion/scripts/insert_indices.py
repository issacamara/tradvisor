import functions_framework

from helper import process_files, load_files

@functions_framework.http
def entry_point(request=None):
    # Load configuration from YAML file
    asset = "indices"
    process_files(None, load_files(None, asset))

    return "Data insertion successfully completed !\n"

if __name__ == "__main__":
    print(entry_point())
