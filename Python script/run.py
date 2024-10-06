import time
import csv
import os
from providers.Phoenix import get_phoenix_components, populate_phoenix_teams, get_auth_token , create_teams, create_team_rules, assign_users_to_team
from providers.Utils import populate_domains, get_subdomains, populate_users_with_all_team_access
from providers.YamlHelper import populate_repositories, populate_teams, populate_hives, populate_subdomain_owners
from providers.Aks import get_subscriptions, get_clusters, get_cluster_images

# Global Variables
resource_folder = os.path.join(os.path.dirname(__file__), 'Resources')
client_id = ""
client_secret = ""
access_token = ""
action_teams = True
action_code = True
action_cloud = True

# Handle command-line arguments or prompt for input
import sys
args = sys.argv[1:]

print("Arguments supplied:", len(args))

if len(args) == 5:
    client_id = args[0]
    client_secret = args[1]

    if args[2].lower() == "false":
        action_teams = False

    if args[3].lower() == "false":
        action_code = False

    if args[4].lower() == "false":
        action_cloud = False

    print(f"Teams: {action_teams}, Code: {action_code}, Cloud: {action_cloud}")
else:
    client_id = input("Please enter clientID: ")
    client_secret = input("Please enter clientSecret: ")

environments = []

# Populate data from various resources
repos = populate_repositories(resource_folder)
domains = populate_domains(repos)
teams = populate_teams(resource_folder)
hive_staff = populate_hives(resource_folder)  # List of Hive team staff
subdomain_owners = populate_subdomain_owners(repos)
subdomains = get_subdomains(repos)

pteams = populate_phoenix_teams(access_token)  # Pre-existing Phoenix teams
all_team_access = []  # Populate users with full team access (this needs to be implemented)


# Display teams
print("[Teams]")
for team in teams:
    try:
        if "Team" in team['AzureDevopsAreaPath']:
            team['TeamName'] = team['AzureDevopsAreaPath'].split("Team")[1].strip()
            print(team['TeamName'])
    except Exception as e:
        print(f"Error: {e}")

# Display domains and repos
print("\n[Domains]")
print(domains)

print("\n[Repos]")
print(repos)

# Define environment data (as dictionaries since Python lacks PowerShell's PSCustomObject)
environments.append({
    'Name': 'Production',
    'Criticality': 1,
    'CloudAccounts': ["", ""]
})

environments.append({
    'Name': 'Development',
    'Criticality': 6,
    'CloudAccounts': []
})

environments.append({
    'Name': 'DevOPS',
    'Criticality': 7,
    'CloudAccounts': [""]
})

environments.append({
    'Name': 'Thirdparty',
    'Criticality': 4,
    'CloudAccounts': [""]
})

environments.append({
    'Name': 'SIM',
    'Criticality': 8,
    'CloudAccounts': []
})

environments.append({
    'Name': 'Staging',
    'Criticality': 9,
    'CloudAccounts': []
})

# Get authentication token
access_token = get_auth_token(client_id, client_secret)

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

phoenix_components = get_phoenix_components(access_token)
pteams = populate_phoenix_teams(access_token)

app_environments = []  # Should be populated using the equivalent PopulateApplicationsAndEnvironments

# Stopwatch logic
start_time = time.time()

# Team actions
if action_teams:
    print("Performing Teams Actions")
    all_team_access = populate_users_with_all_team_access(teams)
    create_teams(teams, pteams, access_token)
    create_team_rules(teams, pteams, access_token)
    assign_users_to_team(pteams, teams, all_team_access, hive_staff, access_token)

    elapsed_time = time.time() - start_time
    print(f"[Diagnostic] [Teams] Time Taken: {elapsed_time}")
    start_time = time.time()

# Cloud actions
if action_cloud:
    print("Performing Cloud Actions")
    for environment in environments:
        if not any(env['Name'] == environment['Name'] and env.get('type') == "ENVIRONMENT" for env in app_environments):
            # Create environments as needed
            print(f"Creating environment: {environment['Name']}")

    # Perform cloud services
    print("[Diagnostic] [Cloud] Time Taken:", time.time() - start_time)
    print("Starting Cloud Asset Rules")
    print("[Diagnostic] [Cloud] Time Taken:", time.time() - start_time)
    print("Starting Third Party Rules")
    
    elapsed_time = time.time() - start_time
    print(f"[Diagnostic] [Cloud] Time Taken: {elapsed_time}")
    start_time = time.time()

# Code actions
if action_code:
    cluster_images = []

    file = "AKSImages.csv"
    subscriptions = get_subscriptions()

    for subscription in subscriptions:
        print(subscription['Name'])
        clusters = get_clusters(subscription)
        for cluster in clusters:
            cluster_images.extend(get_cluster_images(cluster))

        print(f"Total Images Tally: {len(cluster_images)}")

        if cluster_images:
            with open(file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(cluster_images)

        time.sleep(5)

    if os.path.exists(file):
        print(f"Processing {file}")
        with open(file, 'r') as csvfile:
            csv_data = csv.DictReader(csvfile)

            service_lookup = {"workload-identity-webhook": "Compute"}

            for row in csv_data:
                found = False
                if row['Repo']:
                    print(f"Row: {row['Repo']}")
                    if row['Repo'] in service_lookup:
                        environment = next((env for env in environments if row['SubscriptionId'] in env['CloudAccounts']), None)
                        if environment:
                            print(f"Adding container rule for {row['ContainerUrl']} in {environment['Name']}")
                            found = True

                    if not found:
                        repo = next((r for r in repos if r['RepositoryName'] == row['Repo']), None)
                        if repo:
                            print(f"Match found. Subdomain: {repo['Subdomain']}")
                            environment = next((env for env in environments if row['SubscriptionId'] in env['CloudAccounts']), None)
                            if environment:
                                print(f"Environment found: {environment['Name']}")
                                print(f"Adding container rule for {row['ContainerUrl']} in {environment['Name']}")

    # Perform code actions
    print("Performing Code Actions")
    print(f"[Diagnostic] [Code] Time Taken: {time.time() - start_time}")