class Candidate:
    def __init__(self, feature, buffer_distance):
        self.feature = feature
        self.buffer = self.create_buffer(buffer_distance)
        self.infrastructures = {}  # To store counts and scores per infrastructure type
        self.census_data = {}  # To store census data scores
        self.critical_zones = {}  # To store critical zone scores and penalties
        self.final_score = 0

    def create_buffer(self, buffer_distance):
        # Create buffer geometry
        return self.feature.geometry().buffer(buffer_distance, segments=5)

    def update_infrastructure_count(self, infra_type):
        # Initialize the count if not already present
        if infra_type not in self.infrastructures:
            self.infrastructures[infra_type] = {'count': 0, 'score': 0}
        self.infrastructures[infra_type]['count'] += 1

    def set_infrastructure_score(self, infra_type, score):
        if infra_type in self.infrastructures:
            self.infrastructures[infra_type]['score'] = score
        else:
            self.infrastructures[infra_type] = {'count': 0, 'score': score}

    def set_census_data_score(self, variable, score):
        self.census_data[variable] = score

    def set_critical_zone_score(self, zone_type, score):
        self.critical_zones[zone_type] = score

    def calculate_final_score(self):
        # Sum up all the individual scores from infrastructures, census data, and critical zones
        self.final_score = sum(info['score'] for info in self.infrastructures.values())
        self.final_score += sum(self.census_data.values())
        self.final_score += sum(self.critical_zones.values())

    def generate_output_attributes(self):
        # Generate a list of attributes for the output feature
        attributes = [self.feature['id'], self.feature['name']]
        for infra_type, info in self.infrastructures.items():
            attributes.extend([info['count'], info['score']])
        for variable, score in self.census_data.items():
            attributes.append(score)
        for zone_type, score in self.critical_zones.items():
            attributes.append(score)
        attributes.append(self.final_score)
        return attributes
