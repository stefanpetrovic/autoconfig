import base64
import requests
import json
import time
from multipledispatch import dispatch
from providers.Utils import group_repos_by_subdomain, calculate_criticality

APIdomain = "https://api.YOURDOMAIN.securityphoenix.cloud" #change this with your specific domain
DEBUG = False #debug settings to trigger debug output 

def get_auth_token(clientID, clientSecret, retries=3):
    credentials = f"{clientID}:{clientSecret}".encode('utf-8')
    base64_credentials = base64.b64encode(credentials).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {base64_credentials}'
    }
    token_url = f"{APIdomain}/v1/auth/access_token"
    
    print(f"Making request to {token_url} to obtain token.")
    
    for attempt in range(retries):
        try:
            response = requests.get(token_url, headers=headers)
            response.raise_for_status()
            return response.json().get('token')
        except requests.exceptions.RequestException as e:
            print(f"Error obtaining token (Attempt {attempt+1}/{retries}): {e}")
            time.sleep(2)  # Wait for 2 seconds before retrying
    
    print(f"Failed to obtain token after {retries} attempts.")
    exit(1)

def construct_api_url(endpoint):
    return f"{APIdomain}{endpoint}"

def create_environment(environment, headers):
    print("[Environment]")

    payload = {
        "name": environment['Name'],
        "type": "ENVIRONMENT",
        "subType": environment['Type'],
        "criticality": environment['Criticality'],
        "owner": {
            "email": environment['Responsable']
        },
        "tags": []
    }

    # Add status tag
    if environment['Status']:
        payload["tags"].append({"key": "status", "value": environment['Status']})

    # Add team_name tag only if it's provided
    if environment['TeamName']:
        payload["tags"].append({"key": "pteam", "value": environment['TeamName']})
    else:
        print(f"Warning: No team_name provided for environment {environment['Name']}. Skipping pteam tag.")

    try:
        api_url = construct_api_url("/v1/applications")
        print(f"Payload for environment creation: {json.dumps(payload, indent=2)}")
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + Environment added: {environment['Name']}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        print(f'Response content: {response.content}')
        raise

# Function to add services and process rules for the environment
def add_environment_services(repos, subdomains, environments, application_environments, phoenix_components, subdomain_owners, teams, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}

    for environment in environments:
        env_name = environment['Name']
        env_id = get_environment_id(application_environments, env_name)

        print(f"[Services] for {env_name}")

        if environment['Services']:  # Updated key to Services
            for service in environment['Services']:
                team_name = service.get('TeamName', None)
                
                if not team_name:
                    print(f"Warning: Service {service['Service']} has no TeamName, skipping service.")
                    continue

                if not environment_service_exist(env_id, phoenix_components, service['Service']):
                    try:
                        add_service(env_name, service['Service'], service['Tier'], team_name, headers)
                    except NotImplementedError as e:
                        print(f"Error adding service {service['Service']} for environment {env_name}: {e}")
                
                add_service_rule_batch(environment, service, headers)

# AddContainerRule Function
def add_container_rule(image, subdomain, environment_name, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}

    rules = [{
        "name": image,
        "filter": {"keyLike": f"*{image}*"}
    }]
    payload = {
        "selector": {
            "applicationSelector": {"name": environment_name, "caseSensitive": False},
            "componentSelector": {"name": subdomain, "caseSensitive": False}
        },
        "rules": rules
    }


def add_service_rule_batch(environment, service, headers):
    payload = None

    # Handle INFRA services with CIDR association (IP-based)
    if service['Association'] == 'IP' and service['Type'] == 'Infra':
        print(f"Adding Service Rule {service['Service']} to {environment['Name']}, with Association=IP")
        
        cidrs = [cidr.strip() for cidr in service['Association_value'].split(",") if cidr.strip()]
        
        if not cidrs:
            print(f"Error: No valid CIDR values found for {service['Service']}.")
            return
        
        for index, cidr in enumerate(cidrs, start=1):
            # Ensure proper CIDR formatting
            if '/' not in cidr:
                finalCidr = f"{cidr}/32"  # Default to /32 if no CIDR mask provided
            else:
                finalCidr = cidr

            payload = {
                "selector": {
                    "applicationSelector": {
                        "name": environment['Name'],
                        "caseSensitive": False
                    },
                    "componentSelector": {
                        "name": service['Service'],
                        "caseSensitive": False
                    }
                },
                "rules": [
                    {
                        "name": f"CIDR rule for {service['Service']} - {index}",
                        "filter": {
                            "assetType": "INFRA",  # Should be a single string, not an array
                            "cidr": finalCidr
                        }
                    }
                ]
            }
            if DEBUG:
                print(f"Payload being sent for CIDR {finalCidr}: {json.dumps(payload, indent=2)}")

            # Send the request to add the rule
            try:
                api_url = construct_api_url("/v1/components/rules")
                response = requests.post(api_url, headers=headers, json=payload)
                response.raise_for_status()  # This will raise HTTPError for 4xx and 5xx responses
                print(f"+ CIDR Rule {index} for {finalCidr} added to {service['Service']}.")
            except requests.exceptions.HTTPError as e:
                print(f"Error: {e}")
                print(f"Response content: {response.content}")  # Log response content for debugging
                if response.status_code == 400:
                    print("Bad Request: Check if all required fields are provided and valid in the payload.")
                elif response.status_code == 409:
                    print(f" > CIDR Rule for {finalCidr} already exists.")
                else:
                    exit(1)

    # Handle Tag-based association
    elif service['Association'] == 'Tag':
        tag_parts = service['Association_value'].split(':')
        
        if len(tag_parts) == 2 and tag_parts[0] and tag_parts[1]:
            print(f"Adding Service Rule {service['Service']} to {environment['Name']}, with Association=Tag")
            
            payload = {
                "selector": {
                    "applicationSelector": {
                        "name": environment['Name'],
                        "caseSensitive": False
                    },
                    "componentSelector": {
                        "name": service['Service'],
                        "caseSensitive": False
                    }
                },
                "rules": [
                    {
                        "name": f"Tag rule for {service['Service']}",
                        "filter": {
                            "tags": [{"key": tag_parts[0], "value": tag_parts[1]}]
                        }
                    }
                ]
            }
        else:
            print(f"Error: Invalid tag format for {service['Service']}. Expected 'key:value', got {service['Association_value']}")
            return
    
    if not payload:
        print("No valid association type found, skipping rule creation.")
        return
    
    if DEBUG:
        print(f"Payload being sent to /v1rule: {json.dumps(payload, indent=2)}")

    try:
        api_url = construct_api_url("/v1/components/rules")
        if DEBUG:
            print(f"Payload being sent to {api_url}: {json.dumps(payload, indent=2)}")
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"+ Service Rule added for {service['Service']}")
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        print(f"Response content: {response.content}")  # Log response content for debugging
        if response.status_code == 400:
            print("Bad Request: Check if all required fields are provided and valid in the payload.")
        elif response.status_code == 409:
            print(f" > Service Rule {service['Service']} already exists.")
        else:
            exit(1)


# AddServiceRule Function
def add_service_rule(environment, service, tag_name, tag_value, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}


    print(f"Adding Service Rule {service} tag {tag_value}")

    payload = {
        "selector": {
            "applicationSelector": {"name": environment['Name'], "caseSensitive": False},
            "componentSelector": {"name": service, "caseSensitive": False}
        },
        "rules": [{
            "name": f"{tag_name} {tag_value}",
            "filter": {
                "tags": [{"key":tag_name, "value":tag_value}],
                "providerAccountId": environment['CloudAccounts']
            }
        }]
        
    }
    if DEBUG:
            print(f"Payload being sent to /v1rule: {json.dumps(payload, indent=2)}")


def create_applications(applications, application_environments, phoenix_components, headers):
    print('[Applications]')
    for application in applications:
        if not any(env['name'] == application['AppName'] and env['type'] == "APPLICATION" for env in application_environments):
            create_application(application, headers)
        else:
            update_application(application, application_environments, phoenix_components, headers)


def create_application(app, headers):
    payload = {
        "name": app['AppName'],
        "type": "APPLICATION",
        "criticality": app['Criticality'],
        "tags": [],
        "owner": {"email": app['Responsable']}
    }

    for team in app['TeamNames']:
        payload['tags'].append({"key": "pteam", "value": team})
                               
    if DEBUG:
        print(f"Payload being sent to /v1rule: {json.dumps(payload, indent=2)}")


    try:
        api_url = construct_api_url("/v1/applications")
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + Application {app['AppName']} added")
        time.sleep(2)
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Application {app['AppName']} already exists")
        else:
            print(f"Error: {e}")
            print(response.content)
            exit(1)
    
    for component in app['Components']:
        create_custom_component(app['AppName'], component, headers)

def create_custom_component(applicationName, component, headers):
    # Ensure valid tag values by filtering out empty or None 
    tags = [
        {"key": "Status", "value": component['Status']},
        {"key": "Type", "value": component['Type']}
    ]

    for team in component['TeamNames']:
        tags.append({"key": "pteam", "value": team})

    tags = list(filter(lambda tag : tag['value'], tags))

    # Add domain and subdomain tags only if they are not None or empty
    if component.get('Domain'):
        tags.append({"key": "domain", "value": component['Domain']})
    if component.get('SubDomain'):
        tags.append({"key": "subdomain", "value": component['SubDomain']})

    payload = {
        "applicationSelector": {
            "name": applicationName
        },
        "name": component['ComponentName'],
        "criticality": component.get('Criticality', 5),  # Default to criticality 5
        "tags": tags
    }

    if DEBUG:
        print(f"Payload being sent to /v1/components: {json.dumps(payload, indent=2)}")

    api_url = construct_api_url("/v1/components")

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"{component['ComponentName']} component added.")
        time.sleep(2)
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Component {component['ComponentName']} already exists")
        else:
            print(f"Error: {e}")
            print(f"Response content: {response.content}")
            exit(1)

    # Ensure RepositoryName is not None and is iterable
    repository_names = component.get('RepositoryName', [])
    
    # If RepositoryName is not a list but a string, convert it to a list
    if isinstance(repository_names, str):
        repository_names = [repository_names]

    for repo_name in repository_names:
        create_repository_rule(applicationName, component['ComponentName'], repo_name, headers)

def update_application(application, existing_apps_envs, existing_components, headers):
    existing_app = next(filter(lambda app: app['name'] == application['AppName'] and app['type'] == "APPLICATION", existing_apps_envs), None)
    if not existing_app:
        print(f"Unexpected call to the update application, as the application does not exist")
    
    update_application_teams(existing_app, application, headers)

    update_application_crit_owner(application, existing_app, headers)

    for component in application['Components']:
        # if new component, create it, otherwise update repos
        if not next(filter(lambda comp: comp['name'] == component['ComponentName'], existing_components), None):
            create_custom_component(application['AppName'], component, headers)
            continue

        repository_names = component.get('RepositoryName', [])
        if isinstance(repository_names, str):
            repository_names = [repository_names]
        for repo_name in repository_names:
            create_repository_rule(application['AppName'], component['ComponentName'], repo_name, headers)

def update_application_teams(existing_app, application, headers):
    for team in filter(lambda tag: tag.get('key') == 'pteam', existing_app.get('tags')):
        if team.get('value') not in application.get('TeamNames'):
            remove_tag_from_application(team.get('id'), team.get('key'), team.get('value'), existing_app.get('id'), headers)

    for new_team in application.get('TeamNames'):
        if not next(filter(lambda team: team.get('key') == 'pteam' and team['value'] == new_team, existing_app.get('tags')), None):
            add_tag_to_application('pteam', new_team, existing_app.get('id'), headers)

def update_application_crit_owner(application, existing_application, headers):
    if application['Criticality'] == existing_application.get('criticality') and application['Responsable'] == existing_application.get('owner').get('email'):
        if DEBUG:
            print(f"No change detected to update for application {application['AppName']}")
        return
    
    payload = {
        "name": application['AppName'],
        "criticality": application['Criticality'],
        "owner": {"email": application['Responsable']}
    }

    try:
        api_url = construct_api_url(f"/v1/applications/{existing_application.get('id')}")
        response = requests.patch(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Updated application {application['AppName']}.")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        print(f"Response content: {response.content}")
        exit(1)


            
# Handle Repository Rule Creation for Components
def create_repository_rule(applicationName, componentName, repositoryName, headers):
    payload = {
        "selector": {
            "applicationSelector": {"name": applicationName, "caseSensitive": False},
            "componentSelector": {"name": componentName, "caseSensitive": False}
        },
        "rules": [{
            "name": f"Repository rule for {repositoryName}",
            "filter": {"repository": [repositoryName]}
        }]
    }

    if DEBUG:
        print(f"Payload for {componentName}: {json.dumps(payload, indent=2)}")

    try:
        api_url = construct_api_url("/v1/components/rules")
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Rule for {repositoryName} created.")
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Rule for {repositoryName} already exists.")
        else:
            print(f"Error: {e}")
            print(f"Response content: {response.content}")
            exit(1)

def get_repositories_from_component(component):
    if not component['RepositoryName']:
        return []
    
    if type(component['RepositoryName']) == str:
        return [component['RepositoryName']]
    
    return component['RepositoryName']

# CreateRepositories Function
def create_repositories(repos, access_token):
    # Iterate over the list of repositories and call the create_repo function
    for repo in repos:
        create_repo(repo, access_token)

# CreateRepo Function
def create_repo(repo, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Calculate criticality (assuming a function `calculate_criticality` exists)
    criticality = calculate_criticality(repo['Tier'])
    
    # Create the payload, the function assume 1 repo per component with the component name being the repository this can be edited
    payload = {
        "repository": f"{repo['RepositoryName']}",
        "applicationSelector": {
            "name": repo['Subdomain'],
            "caseSensitive": False
        },
        "component": {
            "name": repo['RepositoryName'],
            "criticality": criticality,
            "tags": [
                {"key": "pteam", "value": repo['Team']},
                {"key": "domain", "value": repo['Domain']},
                {"key": "subdomain", "value": repo['Subdomain']}
            ]
        }
    }
    if DEBUG:
        print(f"Payload being sent to /v1rule: {json.dumps(payload, indent=2)}")


    api_url = construct_api_url("/v1/applications/repository")

    try:
        # Make POST request to create the repository
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + {repo['RepositoryName']} added.")
    
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Repo {repo['RepositoryName']} already exists")
        else:
            print(f"Error: {e}")
            exit(1)

# AddCloudAssetRules Function
def add_cloud_asset_rules(repos, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Loop through each repository and modify domain if needed
    for repo in repos:
        search_term = f"*{repo['RepositoryName']}(*"
        cloud_asset_rule(repo['Subdomain'], search_term, "Production", access_token)

    # Adding rules for PowerPlatform with different environments
    #cloud_asset_rule("PowerPlatform", "powerplatform_prod", "Production", access_token)
    #cloud_asset_rule("PowerPlatform", "powerplatform_sim", "Sim", access_token)
    #cloud_asset_rule("PowerPlatform", "powerplatform_staging", "Staging", access_token)
    #cloud_asset_rule("PowerPlatform", "powerplatform_dev", "Development", access_token)

# CloudAssetRule Function
def cloud_asset_rule(name, search_term, environment_name, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Create the payload
    payload = {
        "selector": {
            "applicationSelector": {
                "name": environment_name,
                "caseSensitive": False
            },
            "componentSelector": {
                "name": name,
                "caseSensitive": False
            }
        },
        "rules": [
            {
                "name": name,
                "filter": {
                    "keyLike": search_term
                }
            }
        ]
    }

    api_url = construct_api_url("/v1/components/rules")
    if DEBUG:
        print(f"Payload being sent to /v1rule: {json.dumps(payload, indent=2)}")

    try:
        # Make POST request to add the cloud asset rule
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"> Cloud Asset Rule added for {name} in {environment_name}")
    
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > Cloud Asset Rule for {name} already exists")
        else:
            print(f"Error: {e}")
            print(f"Error details: {response.content}")

def create_teams(teams, pteams, access_token):
    """
    This function iterates through a list of teams and adds new teams if they are not already present in `pteams`.

    Args:
    - teams: List of team objects to be added.
    - pteams: List of existing team objects to check if a team already exists.
    - access_token: Access token for API authentication.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    new_pteams = []
    
    # Iterate over the list of teams to be added
    for team in teams:
        found = False

        # Check if the team already exists in the existing pteams
        for pteam in pteams:
            if pteam['name'] == team['TeamName']:
                found = True
                break
        
        # If the team is not found and has a valid name, proceed to add it
        if not found and team['TeamName']:
            print(f"Going to add {team['TeamName']} team.")
            
            # Prepare the payload for creating the team
            payload = {
                "name": team['TeamName'],
                "type": "GENERAL"
            }

            api_url = construct_api_url("/v1/teams")
            if DEBUG:
                print(f"Payload being sent to /v1teams: {json.dumps(payload, indent=2)}")

            try:
                # Make the POST request to add the team
                response = requests.post(api_url, headers=headers, json=payload)
                response.raise_for_status()
                team['id'] = response.json()['id']
                new_pteams.append(response.json())
                print(f"+ Team {team['TeamName']} added.")
            
            except requests.exceptions.RequestException as e:
                if response.status_code == 400:
                    print(f" > Team {team['TeamName']} already exists")
                else:
                    print(f"Error: {e}")
                    exit(1)
    return new_pteams


def populate_phoenix_teams(access_token):
    """
    This function retrieves the list of Phoenix teams by making a GET request to the /v1/teams endpoint.

    Args:
    - access_token: Access token for API authentication.

    Returns:
    - List of teams if the request is successful, otherwise exits with an error message.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    api_url = construct_api_url("/v1/teams")

    try:
        print("Getting list of Phoenix Teams")
        # Make the GET request to retrieve the list of teams
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        
        # Return the content of the response (team list)
        return response.json().get('content', [])
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        exit(1)


# CreateTeamRules Function
def create_team_rules(teams, pteams, access_token):
    """
    This function iterates through a list of teams and creates team rules for teams
    that do not already exist in `pteams`.

    Args:
    - teams: List of team objects.
    - pteams: List of pre-existing teams to check if a team already exists.
    - access_token: Access token for API authentication.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    for team in teams:
        found = False

        # Check if the team already exists in pteams
        for pteam in pteams:
            if pteam['name'] == team['TeamName']:
                found = True
                break
        
        # If the team does not exist and has a valid name, create the team rule
        if not found and team['TeamName']:
            print(f"Team: {team['TeamName']}")
            create_team_rule("pteam", team['TeamName'], team['id'], access_token)

def create_team_rule(tag_name, tag_value, team_id, access_token):
    """
    This function creates a team rule by adding tags to a team.

    Args:
    - tag_name: Name of the tag (e.g., "pteam").
    - tag_value: Value of the tag (e.g., the team name).
    - team_id: ID of the team.
    - access_token: API authentication token.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Create the payload with the tags
    payload = {
        "match": "ANY",
        "tags": [
            {
                "key": tag_name,
                "value": tag_value
            }
        ]
    }

    api_url = construct_api_url(f"/v1/teams/{team_id}/components/auto-link/tags")
    
    try:
        # Make the POST request to create the team rule
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + {tag_name} Component rule added for: {tag_value}")
    
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > {tag_name} Component Rule {tag_value} already exists")
        else:
            print(f"Error: {e}")
            exit(1)

    api_url = construct_api_url(f"/v1/teams/{team_id}/applications/auto-link/tags")
    
    try:
        # Make the POST request to create the team rule
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + {tag_name} App/Env rule added for: {tag_value}")
    
    except requests.exceptions.RequestException as e:
        if response.status_code == 409:
            print(f" > {tag_name} App/Env Rule {tag_value} already exists")
        else:
            print(f"Error: {e}")
            exit(1)


@dispatch(list,list,list,list,list,str)
def assign_users_to_team(p_teams, new_pteams, teams, all_team_access, hive_staff, access_token):
    """
    This function assigns users to teams by checking if users are already part of the team, and adds or removes them accordingly.
    
    Args:
    - p_teams: List of Phoenix teams.
    - teams: List of target teams to manage.
    - all_team_access: List of users with full team access.
    - hive_staff: List of Hive team staff.
    - access_token: API authentication token.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    all_pteams = p_teams + new_pteams
    for pteam in all_pteams:
        # Fetch current team members from the Phoenix platform
        team_members = get_phoenix_team_members(pteam['id'], headers)

        for team in teams:
            if team['TeamName'] == pteam['name']:
                print(f"[Team] {pteam['name']}")

                # Assign users from AllTeamAccess that are not part of the current team members
                for user_email in all_team_access:
                    found = any(member['email'] == user_email for member in team_members)
                    if not found:
                        api_call_assign_users_to_team(pteam['id'], user_email, headers)

                # Assign team members from the team if they are not part of the current team members
                for team_member in team['TeamMembers']:
                    found = any(member['email'] == team_member['EmailAddress'] for member in team_members)
                    if not found:
                        api_call_assign_users_to_team(pteam['id'], team_member['EmailAddress'], headers)

                # Remove users who no longer exist in the team members
                for member in team_members:
                    found = does_member_exist(member['email'], team, hive_staff, all_team_access)
                    if not found:
                        delete_team_member(member['email'], pteam['id'], headers)

        # Assign Hive team lead and product owners to the team
        hive_team = next((hs for hs in hive_staff if hs['Team'].lower() == pteam['name'].lower()), None)

        if hive_team:
            print(f"> Adding team lead {hive_team['Lead']} to team {pteam['name']}")
            api_call_assign_users_to_team(pteam['id'], hive_team['Lead'], headers)

            for product_owner in hive_team['Product']:
                print(f"> Adding Product Owner {product_owner} to team {pteam['name']}")
                api_call_assign_users_to_team(pteam['id'], product_owner, headers)


# ConstructAPIUrl Function
def construct_api_url(endpoint):
    """
    Constructs the full API URL by appending the endpoint to the base domain.
    
    Args:
    - endpoint: The API endpoint (e.g., "/v1/teams/{team_id}/users").
    
    Returns:
    - Full API URL.
    """
    return f"{APIdomain}{endpoint}"



# APICallAssignUsersToTeam Function
def api_call_assign_users_to_team(team_id, email, access_token):
    """
    Assigns a user to a team by making a PUT request to the API.

    Args:
    - team_id: The ID of the team.
    - email: The email address of the user to be added to the team.
    - access_token: API authentication token.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Construct the payload with the user email
    payload = {
        "users": [
            {"email": email}
        ]
    }
    
    # Construct the full API URL
    api_url = construct_api_url(f"/v1/teams/{team_id}/users")
    
    try:
        # Make the PUT request to assign the user to the team
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + User {email} added to team {team_id}")
    
    except requests.exceptions.RequestException as e:
        if response.status_code == 400:
            print(f" ? Team Member assignment {email} user hasn't logged in yet")
        elif response.status_code == 409:
            print(f" - Team Member {email} already assigned")
        else:
            print(f"Error: {e}")
            exit(1)


# DeleteTeamMember Function
def delete_team_member(email, team_id, access_token):
    """
    Removes a user from a team by making a DELETE request to the API.

    Args:
    - email: The email address of the user to be removed from the team.
    - team_id: The ID of the team.
    - access_token: API authentication token.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    
    # Construct the full API URL
    api_url = construct_api_url(f"/v1/teams/{team_id}/users/{email}")
    
    try:
        # Make the DELETE request to remove the user from the team
        response = requests.delete(api_url, headers=headers)
        response.raise_for_status()
        print(f"- Removed {email} from team {team_id}")
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def get_phoenix_components(access_token):
    """
    Fetches the list of Phoenix components by making GET requests to the /v1/components endpoint.
    Handles pagination to retrieve all components.

    Args:
    - access_token: API authentication token.

    Returns:
    - A list of components.
    """
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    components = []

    print("Getting list of Phoenix Components")

    # Initial API call to get the first page of components
    api_url = construct_api_url("/v1/components")
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Add the components from the first page
        components.extend(data['content'])

        total_pages = data.get('totalPages', 1)

        # Loop through the remaining pages (if any)
        for page in range(1, total_pages):
            api_url = construct_api_url(f"/v1/components/?pageNumber={page}")
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Append components from each page
            components.extend(data['content'])

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

    return components

# Helper function to get team members
def get_phoenix_team_members(team_id, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    api_url = construct_api_url(f"/v1/teams/{team_id}/users")
    
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    return response.json()


def remove_old_tags(phoenix_components, repos, override_list):
    """
    Removes old tags from Phoenix components by comparing the repository information.

    Args:
    - phoenix_components: List of Phoenix components fetched from the API.
    - repos: List of repositories.
    - override_list: List of overrides for repository names and subdomains.
    """
    print("Removing old tags")

    for repo in repos:
        
        # Apply overrides from the override list
        for repo_override in override_list:
            if repo['RepositoryName'] == repo_override['Key']:
                repo['Subdomain'] = repo_override['Value']
        
        # Check and remove old tags in phoenix_components
        for component in phoenix_components:
            if repo['RepositoryName'] == component['name']:
                print(f"Repo: {repo['RepositoryName']}")
                #get_tag_value("domain", component['tags'], repo['Domain'])
                #get_tag_value("subdomain", component['tags'], repo['Subdomain'])
                get_tag_value("pteam", component['tags'], repo['Team'])

def get_tag_value(tag_name, source_tags, expected_value):
    """
    Checks and removes or updates a tag if the current value does not match the expected value.

    Args:
    - tag_name: The name of the tag to check.
    - source_tags: The tags associated with the component.
    - expected_value: The expected value for the tag.
    """
    for tag in source_tags:
        if tag['key'] == tag_name:
            if tag['value'] != expected_value:
                try:
                    print(f"- Removing tag {tag['key']} {tag['value']}")
                    remove_tag(tag['id'], tag_name, tag['value'])
                except Exception as e:
                    print(f"Error removing tag for {tag_name}: {e}")

def remove_tag(tag_id, tag_key, tag_value,access_token):
    """
    Removes the specified tag by making a DELETE or PATCH API call.

    Args:
    - tag_id: The ID of the tag to remove.
    - tag_key: The key of the tag.
    - tag_value: The value of the tag.
    """
    # Payload for removing the tag
    payload = {
        "action": "delete",
        "tags": [
            {
                "id": tag_id,
                "key": tag_key,
                "value": tag_value
            }
        ]
    }
    if DEBUG:
        print(f"Payload being sent to /v1-component-tags: {json.dumps(payload, indent=2)}")

    api_url = construct_api_url("/v1/components/tags")
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}

    try:
        response = requests.patch(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Tag {tag_key} with value {tag_value} removed successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error removing tag: {e}")

def remove_tag_from_application(tag_id, tag_key, tag_value, application_id, headers):
    """
    Removes the specified tag by making a DELETE or PATCH API call.

    Args:
    - tag_id: The ID of the tag to remove.
    - tag_key: The key of the tag.
    - tag_value: The value of the tag.
    - application_id: The ID of the application having the tag
    """
    # Payload for removing the tag
    payload = {
        "action": "delete",
        "tags": [
            {
                "id": tag_id,
                "key": tag_key,
                "value": tag_value
            }
        ]
    }
    if DEBUG:
        print(f"Payload being sent to /v1-application-tags: {json.dumps(payload, indent=2)}")

    api_url = construct_api_url(f"/v1/applications/{application_id}/tags")


    try:
        response = requests.patch(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Tag {tag_key} with value {tag_value} removed successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error removing tag: {e}")

def add_tag_to_application(tag_key, tag_value, application_id, headers):
    """
    Add the specified tag by making a PUT API call.

    Args:
    - tag_key: The key of the tag.
    - tag_value: The value of the tag.
    - application_id: The application to tag
    """
    # Payload for removing the tag
    payload = {
        "tags": [
            {
                "key": tag_key,
                "value": tag_value
            }
        ]
    }
    if DEBUG:
        print(f"Payload being sent to /v1-application-tags: {json.dumps(payload, indent=2)}")

    api_url = construct_api_url(f"/v1/applications/{application_id}/tags")


    try:
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Tag {tag_key} with value {tag_value} added successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error adding tag: {e}")

# Helper function to assign users to a team
def api_call_assign_users_to_team(team_id, user_email, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    payload = {
        "users": [{"email": user_email}]
    }

    api_url = construct_api_url(f"/v1/teams/{team_id}/users")
    
    response = requests.put(api_url, headers=headers, json=payload)
    response.raise_for_status()
    print(f" + User {user_email} added to team {team_id}")

# Helper function to delete team members
def delete_team_member(user_email, team_id, access_token):
    headers = {'Authorization': f"Bearer {access_token}", 'Content-Type': 'application/json'}
    api_url = construct_api_url(f"/v1/teams/{team_id}/users/{user_email}")

    response = requests.delete(api_url, headers=headers)
    response.raise_for_status()
    print(f"- Removed {user_email} from team {team_id}")

# Helper function to check if a member exists
@dispatch(str,dict,list,list)
def does_member_exist(user_email, team, hive_staff, all_team_access):
    """
    Checks if a team member exists in the provided lists (team, hive_staff, or all_team_access).
    """
    return any(user_email == member['EmailAddress'] for member in team['TeamMembers']) or \
           user_email in all_team_access or \
           any(user_email == staff_member['Lead'] or user_email in staff_member['Product'] for staff_member in hive_staff)



#other supporting functions 

def populate_applications_and_environments(headers):
    components = []

    try:
        print("Getting list of Phoenix Applications and Environments")
        api_url = construct_api_url("/v1/applications")
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()

        data = response.json()
        components = data.get('content', [])
        total_pages = data.get('totalPages', 1)

        for i in range(1, total_pages):
            api_url = construct_api_url(f"/v1/applications?pageNumber={i}")
            response = requests.get(api_url, headers=headers)
            components += response.json().get('content', [])
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        exit(1)

    return components

# Add the default function to handle NoneType for team (when team is missing)
@dispatch(str, str, int, dict)
def add_service(applicationSelectorName, service, tier, headers):
    criticality = calculate_criticality(tier)
    print(f" > Attempting to add {service} without specific team")
    
    payload = {
        "name": service,
        "criticality": criticality,
        "applicationSelector": {
            "name": applicationSelectorName
        },
        "tags": []  # No team tag since it's missing
    }

    if DEBUG:
            print(f"Payload being sent to /v1components: {json.dumps(payload, indent=2)}")

    api_url = construct_api_url("/v1/components")
    response = requests.post(api_url, headers=headers, json=payload)
    response.raise_for_status()
    print(f" + Added Service: {service}")
    time.sleep(2)

# Dispatch version for when all arguments, including team, are provided
@dispatch(str, str, int, str, dict)
def add_service(applicationSelectorName, service, tier, team, headers):
    criticality = calculate_criticality(tier)
    print(f" > Attempting to add {service} for team {team}")
    
    payload = {
        "name": service,
        "criticality": criticality,
        "applicationSelector": {
            "name": applicationSelectorName
        },
        "tags": [{"key": "pteam", "value": team}]
    }

    api_url = construct_api_url("/v1/components")
    response = requests.post(api_url, headers=headers, json=payload)
    response.raise_for_status()
    print(f" + Added Service: {service}")
    time.sleep(2)

@dispatch(str,dict,dict)
def does_member_exist(email, team, headers):
    """
    Check if a member with a specific email exists in the given team.
    """
    try:
        team_members = get_phoenix_team_members(team["id"], headers)
        return any(member['email'].lower() == email.lower() for member in team_members)
    except Exception as e:
        print(f"Error checking if member exists: {e}")
        return False

def add_thirdparty_services(phoenix_components, application_environments, subdomain_owners, headers):
    services = [
        "Salesforce", #example of 3rd party app to add components and findings to 3rd parties
    ]

    env_name = "Thirdparty"
    env_id = get_environment_id(application_environments, env_name)

    if not env_id:
        print('Environment Thirdparty not found')
        return

    for service in services:
        if not environment_service_exist(env_id, phoenix_components, service):
            add_service(env_name, service, 5, "Thirdparty", subdomain_owners, headers)

def get_environment_id(application_environments, env_name):
    for environment in application_environments:
        if environment["name"] == env_name:
            return environment["id"]
    return None

def environment_service_exist(env_id, phoenix_components, service_name):
    for component in phoenix_components:
        if component['name'] == service_name and component['applicationId'] == env_id:
            return True
    return False

def get_phoenix_team_members(team_id, headers):
    try:
        api_url = construct_api_url(f"/v1/teams/{team_id}/users")
        response = requests.get(api_url, headers=headers)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return []

def api_call_assign_users_to_team(team_id, email, headers):
    payload = {"users": [{"email": email}], "autoCreateUsers": True}

    try:
        api_url = construct_api_url(f"/v1/teams/{team_id}/users")
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print(f" + User {email} added to team")
    except requests.exceptions.RequestException as e:
        if response.status_code == 400:
            print(f" ? Team Member assignment {email} user hasn't logged in yet")
        elif response.status_code == 409:
            print(f" - Team Member already assigned {email}")
        else:
            print(f"Error: {e}")
            exit(1)

def delete_team_member(email, team_id, headers):
    try:
        api_url = construct_api_url(f"/v1/teams/{team_id}/users/{email}")
        response = requests.delete(api_url, headers=headers)
        response.raise_for_status()
        print(f"- Removed {email} from team")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

