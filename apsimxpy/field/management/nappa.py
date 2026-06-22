import json
from ...utils import ApsimModifier
import os


class Nappa(ApsimModifier):
    def __init__(self, init_obj=None):
        self.apsim_file_input = init_obj.apsim_file_input
        self.apsim_folder_input = init_obj.apsim_folder_input
        apsim_file = open(
            os.path.join(self.apsim_folder_input, f"{self.apsim_file_input}.apsimx"), "r"
        )
        apsim_json = apsim_file.read()
        self.modifier = json.loads(apsim_json)

        children = self.modifier["Children"][0]["Children"]
        zones = next(
            child for child in children
            if child["$type"] == "Models.Core.Zone, Models"
        )
        params = next(
            prop for prop in zones["Children"]
            if prop["Name"] == "nappa"
        )["Parameters"]
        water_table_depth = next(
            param for param in params if param["Key"] == "WaterTableDepth"
        )

        self.__water_table_depth = water_table_depth["Value"]

    def _reload(self):
        apsim_file = open(
            os.path.join(self.apsim_folder_input, f"{self.apsim_file_input}.apsimx"), "r"
        )
        apsim_json = apsim_file.read()
        self.modifier = json.loads(apsim_json)
        children = self.modifier["Children"][0]["Children"]
        zones = next(
            child for child in children
            if child["$type"] == "Models.Core.Zone, Models"
        )
        self.params = next(
            prop for prop in zones["Children"]
            if prop["Name"] == "nappa"
        )["Parameters"]

    def save_changes(self):
        with open(
            os.path.join(self.apsim_folder_input, f"{self.apsim_file_input}.apsimx"), "w"
        ) as f:
            json.dump(self.modifier, f, indent=4)

    def set_water_table_depth(self, new_value):
        self._reload()

        water_table_depth = next(
            param for param in self.params if param["Key"] == "WaterTableDepth"
        )
        water_table_depth["Value"] = str(new_value)
        self.save_changes()
        self.__water_table_depth = new_value

    def get_water_table_depth(self):
        return self.__water_table_depth