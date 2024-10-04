import requests
import base64
import json

# Base API domain for Phoenix
API_DOMAIN = "https://api.YOURDOMAIN.securityphoenix.cloud"

# Utility function to construct API URLs
def construct_api_url(endpoint):
    return f"{API_DOMAIN}{endpoint}"

# Get Access Token
def get_auth_token(client_id, client_secret):
    """
    Function to obtain the access token for Phoenix API using Client ID and Client Secret.
    """
    auth_string = f"{client_id}:{client_secret}"
    auth_encoded = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_encoded}"
    }

    token_url = construct_api_url('/v1/auth/access_token')
    print(f"Making request to {token_url} to obtain token.")

    try:
        response = requests.get(token_url, headers=headers)
        response.raise_for_status()
        access_token = response.json().get("token")
        print("Access token obtained")
        return access_token
    except requests.exceptions.RequestException as e:
        print(f"Error obtaining token: {e}")
        exit(1)

# Create Environments
def create_environment(name, criticality, env_type, headers):
    print(f"[Environment] Adding environment: {name}")

    payload = {
        "name": name,
        "type": "ENVIRONMENT",
        "subType": env_type,
        "criticality": criticality,
        "owner": {"email": "owner@company.com"}
    }

    api_url = construct_api_url("/v1/applications")
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + Environment added: {name}")
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Environment {name} already exists")
        else:
            print(f"Error adding environment: {e}")
            exit(1)

# Populate Applications and Environments
def populate_applications_and_environments(headers):
    components = []

    print("Getting list of Phoenix Applications and Environments")
    api_url = construct_api_url("/v1/applications")
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        components.extend(data.get("content", []))

        total_pages = data.get("totalPages", 1)

        for i in range(1, total_pages):
            page_url = construct_api_url(f"/v1/applications?pageNumber={i}")
            response = requests.get(page_url, headers=headers)
            response.raise_for_status()
            components.extend(response.json().get("content", []))

    except requests.exceptions.RequestException as e:
        print(f"Error fetching applications and environments: {e}")
        exit(1)

    return components

# Add Environment Services
def add_environment_services(environments, subdomains, application_environments, phoenix_components, subdomain_owners, teams, headers):
    for environment in environments:
        env_name = environment['Name']
        env_id = get_environment_id(application_environments, env_name)

        print(f"[Services] for {env_name}")

        if environment.get("CloudAccounts"):
            for subdomain in subdomains:
                if not environment_service_exist(env_id, phoenix_components, subdomain['Name']):
                    add_service(env_name, subdomain['Name'], subdomain['Tier'], subdomain['Domain'], subdomain_owners, headers)

            if not environment_service_exist(env_id, phoenix_components, "Databricks"):
                add_service(env_name, "Databricks", 5, "YOURDOMAIN Data", subdomain_owners, headers)

            # Add other rules as needed, based on your specific implementation
            # AddServiceRuleBatch, AddServiceRule, etc.

# Add Service
def add_service(environment, service, tier, domain, subdomain_owners, headers):
    print(f"> Attempting to add {service}")

    if domain == "FX":
        domain = "Foreign Exchange(FX)"

    criticality = calculate_criticality(tier)

    payload = {
        "name": service,
        "criticality": criticality,
        "tags": [],
        "applicationSelector": {"name": environment}
    }

    for team in subdomain_owners.get(service, []):
        payload["tags"].append({"key": "pteam", "value": team})

    payload["tags"].append({"key": "domain", "value": domain})

    api_url = construct_api_url("/v1/components")
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + Added Service {service}")
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Service {service} already exists")
        else:
            print(f"Error adding service: {e}")
            exit(1)

# Main function
def main():
    # API Credentials
    client_id = input("Enter Phoenix Client ID: ")
    client_secret = input("Enter Phoenix Client Secret: ")

    # Get access token
    access_token = get_auth_token(client_id, client_secret)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Example usage: creating environments, adding services, etc.
    create_environment("Production", 5, "ENVIRONMENT", headers)

    # Populate applications and environments
    components = populate_applications_and_environments(headers)
    print(f"Components found: {len(components)}")

if __name__ == "__main__":
    main()