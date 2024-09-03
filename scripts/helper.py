import os
import pandas as pd
from google.cloud import storage
def save_dataframe_as_csv(df, filename, gcs_bucket_name=None):
    """
    Save a Pandas DataFrame as a CSV file either locally or to Google Cloud Storage (GCS).

    Parameters:
    - df (pd.DataFrame): The DataFrame to save.
    - filename (str): The name of the file to save as.
    - gcs_bucket_name (str, optional): The name of the GCS bucket. If provided, the file will be saved to GCS.
      If None, the file will be saved locally.
    """
    if gcs_bucket_name:
        # Save the file to a temporary location
        temp_filename = f'/tmp/{filename}'
        df.to_csv(temp_filename, index=False)

        # Upload the file to GCS
        client = storage.Client()
        bucket = client.bucket(gcs_bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_filename(temp_filename)

        # Optionally, remove the local temp file after upload
        os.remove(temp_filename)

        print(f"File saved to GCS bucket '{gcs_bucket_name}' as '{filename}'.")
    else:
        # Save the file locally
        df.to_csv(filename, index=False)
        print(f"File saved locally as '{filename}'.")


# Example usage:
file_content = "Hello, world!"
file_name = "example.txt"

import pandas as pd

# Create a dictionary with data
data = {
    'Name': ['Alice', 'Bob', 'Charlie'],
    'Age': [25, 30, 35],
    'City': ['New York', 'Los Angeles', 'Chicago']
}

# Create a DataFrame using the dictionary
df = pd.DataFrame(data)

# Save locally
save_dataframe_as_csv(df, 'sample.csv')