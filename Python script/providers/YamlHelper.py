import os
import yaml
from pathlib import Path
from providers.Utils import calculate_criticality
from email_validator import validate_email, EmailNotValidError

# Check if PyYAML module exists
try:
    import yaml
    print("Module exists")
except ImportError:
    print("Module does not exist. Installing...")
    os.system('pip install pyyaml')


# Function to populate repositories
def populate_repositories(resource_folder):
    repos = []

    if not resource_folder:
        print("Please supply path for the resources")
        return repos

    core_structure = os.path.join(resource_folder, "core-structure.yaml")

    with open(core_structure, 'r') as stream:
        repos_yaml = yaml.safe_load(stream)

    for deployment_group in repos_yaml['DeploymentGroups']:
        if 'BuildDefinitions' not in deployment_group:
            continue
        
        for row in deployment_group['BuildDefinitions']:
            repositoryNames = row.get('RepositoryName', [])
            
            # Check if repositoryNames is a string, if so convert to list
            if isinstance(repositoryNames, str):
                repositoryNames = [repositoryNames]
            
            # Ensure repositoryNames is iterable
            if not isinstance(repositoryNames, list):
                print(f"Warning: RepositoryName is not in an expected format for row: {row}")
                continue

            for repositoryName in repositoryNames:
                print(f'Created repository {repositoryName}')
                item = {
                    'RepositoryName': repositoryName,
                    'Domain': row['Domain'],
                    'Tier': row.get('Tier', 5),
                    'Subdomain': row['SubDomain'],
                    'Team': row['TeamName'],
                    'BuildDefinitionName': row['BuildDefinitionName']
                }
                repos.append(item)

    return repos


# Function to populate environments
def populate_environments_from_env_groups(resource_folder):
    envs = []

    if not resource_folder:
        print("Please supply path for the resources")
        return envs

    banking_core = os.path.join(resource_folder, "core-structure.yaml")

    with open(banking_core, 'r') as stream:
        repos_yaml = yaml.safe_load(stream)

    for row in repos_yaml['Environment Groups']:
        # Check if TeamName exists, otherwise, log and continue.
        if not 'TeamName' in row:
            print(f"Skipping environment {row['Name']}, as TeamName is missing.")
            continue

        # Define the environment item
        item = {
            'Name': row['Name'],
            'Type': row['Type'],
            'Criticality': calculate_criticality(row['Tier']),
            'CloudAccounts': [""],  # Add CloudAccounts if applicable
            'Status': row['Status'],
            'Responsable': row['Responsable'],
            'TeamName': row.get('TeamName', None),  # Add TeamName from the environment or set as None
            'Services': []  # To populate services later
        }

        # Now process the services under the "Team" or "Services" key
        if 'Services' in row:
            for service in row['Services']:
                # Build the service entry with association details
                service_entry = {
                    'Service': service['Service'],
                    'Type': service['Type'],
                    'Association': service['Association'],
                    'Association_value': service['Association_value'],
                    'Tier': service.get('Tier', 5),  # Default tier to 5 if not specified
                    'TeamName': service.get('TeamName', item['TeamName'])  # Default to environment's TeamName if missing
                }
                item['Services'].append(service_entry)

        # Append the environment entry to the list of environments
        envs.append(item)

    return envs

# Function to populate subdomain owners
def populate_subdomain_owners(repos):
    subdomains = {}

    for repo in repos:
        print(repo['RepositoryName'])

        if repo['Subdomain'] not in subdomains:
            subdomains[repo['Subdomain']] = []

        if repo['Team'] not in subdomains[repo['Subdomain']]:
            subdomains[repo['Subdomain']].append(repo['Team'])

    return subdomains


# Function to populate teams

# Example of populating repositories - already in place, no changes needed unless additional processing is required

# Function to populate teams
def populate_teams(resource_folder):
    teams = []

    if not resource_folder:
        print("Please supply path for the resources")
        return teams

    teams_file_path = os.path.join(resource_folder, "Teams")

    if not os.path.exists(teams_file_path):
        print(f"Path does not exist: {teams_file_path}")
        exit(1)

    for team_file in Path(teams_file_path).glob("*.yaml"):
        with open(team_file, 'r') as stream:
            team = yaml.safe_load(stream)

        found = False
        for t in teams:
            if t['TeamName'] == team['TeamName']:
                found = True
                break

        if not found:
            teams.append(team)

    return teams


# Function to populate hives
def populate_hives(resource_folder):
    hives = []

    if not resource_folder:
        print("Please supply path for the resources")
        return hives

    yaml_file = os.path.join(resource_folder, "hives.yaml")

    if not os.path.exists(yaml_file):
        print(f"File not found or invalid path: {yaml_file}")
        return hives

    with open(yaml_file, 'r') as stream:
        yaml_content = yaml.safe_load(stream)

    is_custom_email = yaml_content.get('CustomEmail', False)
    company_email_domain = yaml_content.get('CompanyEmailDomain', None)
    if not is_custom_email and not company_email_domain:
        company_email_domain = input('Please enter company email domain (without @ symbol):')

    for hive in yaml_content['Hives']:
        for team in hive['Teams']:
            products = []
            if team.get('Product'):
                products = [conditionally_replace_first_last_name_with_email(is_custom_email, company_email_domain, p)
                            for p in team['Product'].split(' and ')]

            hive_object = {
                'Lead': conditionally_replace_first_last_name_with_email(is_custom_email, company_email_domain, team['Lead']),
                'Product': products,
                'Team': team['Name']
            }

            hives.append(hive_object)

    return hives

# If is_custom_email=True, only validate the emails and don't replace anything
def conditionally_replace_first_last_name_with_email(is_custom_email, company_email_domain, first_last_name_or_email):
    if (is_custom_email):
        try:
            result = validate_email(first_last_name_or_email)
            return
        except EmailNotValidError as e:
            print(str(e))
            exit(1)

    
    return first_last_name_or_email.strip().lower().replace(" ", ".") + "@" + company_email_domain


def populate_all_access_emails(resource_folder):
    all_access_emails = []

    if not resource_folder:
        print("Please supply path for the resources")
        return all_access_emails

    core_structure = os.path.join(resource_folder, "core-structure.yaml")

    with open(core_structure, 'r') as stream:
        repos_yaml = yaml.safe_load(stream)

    return repos_yaml['AllAccessAccounts']

# Populate applications

# Populate applications
def populate_applications(resource_folder):
    apps = []

    if not resource_folder:
        print("Please supply path for the resources")
        return apps

    core_structure = os.path.join(resource_folder, "core-structure.yaml")

    with open(core_structure, 'r') as stream:
        apps_yaml = yaml.safe_load(stream)

    for row in apps_yaml['DeploymentGroups']:
        if not 'TeamNames' in row:
            print(f"Skipping application {row['AppName']}, as TeamNames are missing.")
            continue

        app = {
            'AppName': row['AppName'],
            'Status': row.get('Status', None),
            'TeamNames': row['TeamNames'],
            'ReleaseDefinitions': row['ReleaseDefinitions'],
            'Responsable': row['Responsable'],
            'Criticality': calculate_criticality(row.get('Tier', 5)),  # Use .get() to handle missing 'Tier'
            'Components': []
        }

        if not 'Components' in row:
            continue

        for component in row['Components']:
            # Handle RepositoryName properly
            repository_names = component.get('RepositoryName', [])
            if isinstance(repository_names, str):
                repository_names = [repository_names]

            comp = {
                'ComponentName': component['ComponentName'],
                'Status': component.get('Status', None),
                'Type': component.get('Type', None),
                'TeamNames': component.get('TeamNames', app['TeamNames']),  # Fallback to app's TeamNames if missing
                'RepositoryName': repository_names,  # Properly handle missing 'RepositoryName'
                'Criticality': calculate_criticality(component.get('Tier', 5)),  # Handle missing 'Tier'
                'Domain': component.get('Domain', None),  # Handle missing 'Domain'
                'SubDomain': component.get('SubDomain', None),  # Handle missing 'SubDomain'
                'AutomaticSecurityReview': component.get('AutomaticSecurityReview', None)  # Handle missing 'AutomaticSecurityReview'
            }
            app['Components'].append(comp)
        apps.append(app)

    return apps