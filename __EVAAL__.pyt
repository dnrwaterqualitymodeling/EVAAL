import sys
sys.path.append(sys.path[0] + '/lib')
import toolClasses
from toolClasses import *

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "__EVAAL__"
        self.alias = ""
        # List of tool classes associated with this toolbox
        self.tools = [conditionTheLidarDem,
            downloadPrecipitationData,
            createCurveNumberRaster,
            internallyDrainingAreas,
            demReconditioning,
            calculateStreamPowerIndex,
            rasterizeKfactorForUsle,
            rasterizeCfactorForUsle,
            calculateSoilLossUsingUsle,
            erosionScore]
