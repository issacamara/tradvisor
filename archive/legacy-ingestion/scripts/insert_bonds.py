import functions_framework
from helper import load_files, process_files


@functions_framework.http
def entry_point(request=None):
    asset = "bonds"
    process_files(None, load_files(None, asset))

    return "Data insertion successfully completed !\n"

if __name__ == "__main__":
    print(entry_point())
