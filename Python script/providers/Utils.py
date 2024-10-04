# Function to populate unique domains from a list of repos
def populate_domains(repos):
    domains = []
    for repo in repos:
        for dom in repo['Domain']:
            if dom not in domains:
                domains.append(dom)
    return domains

# Function to retrieve unique subdomains from repos
def get_subdomains(repos):
    subdomains = []
    for repo in repos:
        if not any(item['Name'] == repo['Subdomain'] for item in subdomains):
            item = {
                'Name': repo['Subdomain'],
                'Domain': repo['Domain'],
                'Tier': repo['Tier']
            }
            subdomains.append(item)
    return subdomains

# Function to get the environment ID based on environment name
def get_environment_id(application_environments, environment_name):
    env = next((env for env in application_environments if env['name'] == environment_name and env['type'] == 'ENVIRONMENT'), None)
    return env['id'] if env else None

# Function to check if a service exists in a given environment
def environment_service_exist(env_id, phoenix_components, servicename):
    for component in phoenix_components:
        if component['applicationId'] == env_id and component['name'] == servicename:
            return True
    return False



# Function to calculate criticality based on tier value
def calculate_criticality(tier):
    criticality = 5
    if tier == "0":
        criticality = 10
    elif tier == "1":
        criticality = 9
    elif tier == "2":
        criticality = 8
    elif tier == "3":
        criticality = 7
    elif tier == "4":
        criticality = 6
    return criticality

# Function to calculate criticality based on tier value
def calculate_criticality(tier):
    criticality = 5
    if tier == "0":
        criticality = 10
    elif tier == "1":
        criticality = 9
    elif tier == "2":
        criticality = 8
    elif tier == "3":
        criticality = 7
    elif tier == "4":
        criticality = 6
    return criticality

# Function to populate users who have access to all teams
def populate_users_with_all_team_access(teams):
    print("Populating the users with all team Access")
    all_access = []
    for team in teams:
        try:
            if team['TeamName'] in ["staffs", "principals", "directors"]:
                for member in team['TeamMembers']:
                    all_access.append(member['EmailAddress'])
        except Exception as e:
            print(str(e))
            exit(1)
    all_access.append("bernard.wright@clear.bank")
    return all_access

# Function to check if a member exists in the given team or override list
def does_member_exist(email, team, hive_staff, all_team_access):
    override_list = ["russell.miles@clear.bank", "neil.syrett@clear.bank"]
    
    if email in override_list or email in all_team_access:
        return True
    
    for member in team['TeamMembers']:
        if email == member['EmailAddress']:
            return True
    
    hive_staff_member = next((staff for staff in hive_staff if staff['Lead'] == email or email in staff['Product']), None)
    
    return hive_staff_member is not None