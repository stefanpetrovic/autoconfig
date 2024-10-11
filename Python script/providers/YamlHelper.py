import os
import yaml
from pathlib import Path
from providers.Utils import calculate_criticality

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

    banking_core = os.path.join(resource_folder, "core-structure.yaml")

    with open(banking_core, 'r') as stream:
        repos_yaml = yaml.safe_load(stream)

    for deployment_group in repos_yaml['DeploymentGroups']:
        if 'BuildDefinitions' not in deployment_group:
            continue
        
        for row in deployment_group['BuildDefinitions']:
            repositoryNames = row['RepositoryName']
            if isinstance(repositoryNames, str):
                item = {
                    'RepositoryName': repositoryNames,
                    'Domain': row['Domain'],
                    'Tier': row['Tier'],
                    'Subdomain': row['SubDomain'],
                    'Team': row['TeamName'],
                    'BuildDefinitionName': row['BuildDefinitionName']
                }
                repos.append(item)
                continue

            for repositoryName in repositoryNames:
                print(f'Created repository {repositoryName}')
                item = {
                    'RepositoryName': repositoryName,
                    'Domain': row['Domain'],
                    'Tier': row['Tier'],
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
        if not 'TeamName' in row:
            print(f'Skipping environment {row['Name']}, as TeamName is missing.')
            continue

        item = {
            'Name': row['Name'],
            'Type': row['Type'],
            'Criticality': calculate_criticality(row['Tier']),
            'CloudAccounts': [""],
            'Status': row['Status'],
            'Responsable': row['Responsable'],
            'TeamName': row['TeamName'],
            'Team': []
        }
        for team in row['Team']:
            service = {
                'Service': team['Service'],
                'Type': team['Type'],
                'Association': team['Association'],
                'Association_value': team['Association_value'],
                'Tier': team['Tier'],
                'TeamName': team['TeamName'] if team['TeamName'] else item['TeamName']
            }
            item['Team'].append(service)
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

    for hive in yaml_content['Hives']:
        for team in hive['Teams']:
            products = []
            if team.get('Product'):
                products = [p.strip().lower().replace(" ", ".") + "@company.com"
                            for p in team['Product'].split(' and ')]

            hive_object = {
                'Lead': team['Lead'].strip().lower().replace(" ", ".") + "@company.com",
                'Product': products,
                'Team': team['Name']
            }

            hives.append(hive_object)

    return hives

def populate_all_access_emails(resource_folder):
    all_access_emails = []

    if not resource_folder:
        print("Please supply path for the resources")
        return all_access_emails

    banking_core = os.path.join(resource_folder, "core-structure.yaml")

    with open(banking_core, 'r') as stream:
        repos_yaml = yaml.safe_load(stream)

    return repos_yaml['AllAccessAccounts']