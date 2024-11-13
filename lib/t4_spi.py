import arcpy
from arcpy import env
from arcpy.sa import *
import math

def spi(dem_cond, dem_recond, fac_max, out_file):
   
    env.snapRaster = dem_cond
    env.extent = dem_cond
    env.cellSize = Raster(dem_cond).meanCellHeight
    env.mask = dem_cond

    arcpy.AddMessage('Calculating slope...')
    G = Slope(dem_cond, "DEGREE") * (math.pi / 180.0)
    arcpy.AddMessage('Calculating flow accumulation...')
    fac = FlowAccumulation(FlowDirection(dem_recond))
    arcpy.AddMessage('Removing flow accumulation pixels above threshold...')
    facLand = Plus(Con(fac < fac_max, fac), 1.0)
    arcpy.AddMessage('Converting flow accumulation to contributing area...')
    CA = facLand * float(env.cellSize)**2

    del fac, facLand
    arcpy.AddMessage('Calculating stream power index...')
    innerTerm = Con(BooleanAnd(IsNull(CA * Tan(G)),(Raster(dem_cond) > 0)),1,((CA * Tan(G)) + 1))

    spi = Ln(innerTerm)
    spi.save(out_file)
