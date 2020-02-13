import arcpy
from arcpy import env
from arcpy.sa import *
import math

def spi(demFile, fillFile, facThreshold, outFile):
   
    env.snapRaster = demFile
    env.extent = demFile
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    env.mask = demFile

    arcpy.AddMessage('Calculating slope...')
    G = Slope(demFile, "DEGREE") * (math.pi / 180.0)
    arcpy.AddMessage('Calculating flow accumulation...')
    fac = FlowAccumulation(FlowDirection(fillFile))
    arcpy.AddMessage('Removing flow accumulation pixels above threshold...')
    facLand = Plus(Con(fac < facThreshold, fac), 1.0)
    arcpy.AddMessage('Converting flow accumulation to contributing area...')
    CA = facLand * float(env.cellSize)**2

    del fac, facLand
    arcpy.AddMessage('Calculating stream power index...')
    innerTerm = Con(BooleanAnd(IsNull(CA * Tan(G)),(Raster(demFile) > 0)),1,((CA * Tan(G)) + 1))

    spi = Ln(innerTerm)
    spi.save(outFile)
