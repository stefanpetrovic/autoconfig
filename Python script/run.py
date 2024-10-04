import json
import requests

def construct_api_url(component_id):
    """
    Construct the API URL for accessing component tags.
    """
    base_url = "https://your-api-url.com/v1/components/"
    return f"{base_url}{component_id}/tags"

def remove_tag(component, tag, headers):
    """
    Removes the tag from the given component using a PATCH request.
    """
    try:
        # Prepare payload for the API request
        payload = {
            "action": "delete",
            "tags": [
                {
                    "id": tag["id"],
                    "key": tag["key"],
                    "value": tag["value"]
                }
            ]
        }

        # Convert payload to JSON
        payload_json = json.dumps(payload, indent=2)

        print(f"- Removing tag {tag['key']} {tag['value']}")

        # Construct API URL
        api_url = construct_api_url(component["id"])

        # Make the PATCH request
        response = requests.patch(api_url, headers=headers, data=payload_json)

        # Check for response status code
        if response.status_code == 200:
            print(f"Tag {tag['key']} {tag['value']} removed successfully.")
        else:
            print(f"Failed to remove tag: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error removing tag for component: {component['name']}")
        print(f"Exception: {str(e)}")


# Example of calling the remove_tag function
if __name__ == "__main__":
    # Sample component and tag data
    component = {
        "id": "component123",
        "name": "Sample Component"
    }

    tag = {
        "id": "tag123",
        "key": "environment",
        "value": "production"
    }

    # Example headers (authentication, content type, etc.)
    headers = {
        "Authorization": "Bearer YOUR_ACCESS_TOKEN",
        "Content-Type": "application/json"
    }

    # Remove the tag
    remove_tag(component, tag, headers)