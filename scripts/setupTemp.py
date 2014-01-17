import arcpy, os, sys, shutil
from arcpy import env

tempDir = sys.path[0] + '/scratch'
tempGdb = tempDir + '/scratch.gdb'
if not os.path.exists(tempGdb):
	arcpy.AddMessage(' ')
	arcpy.AddMessage('Creating scratch space...')
	arcpy.AddMessage(' ')
	arcpy.CreateFileGDB_management(tempDir, 'scratch.gdb', 'CURRENT')
else:
	env.workspace = tempGdb
	tempFiles = arcpy.ListDatasets()
	arcpy.AddMessage(' ')
	arcpy.AddMessage('#################')
	arcpy.AddMessage('Cleaning scratch space...')
	for tempFile in tempFiles:
		arcpy.AddMessage('Deleting ' + tempFile + '...')
		try:
			arcpy.Delete_management(tempFile)
		except:
			arcpy.AddMessage('Cannot clean temporary geodatabase. Are you viewing files in the database with a different application? If yes, please close those applications and re-run the tool. If that does not work, delete the temporary geodatabase (/scripts/temp/temp.gdb) and re-run the tool')
	arcpy.Compact_management(tempGdb)
	os.chdir(tempDir)
	fileList = os.listdir('.')
	for f in fileList:
		if os.path.isdir(f) and f != 'scratch.gdb':
			arcpy.AddMessage('Deleting ' + f + '...')
			shutil.rmtree(f)
		elif f != 'scratch.gdb':
			arcpy.AddMessage('Deleting ' + f + '...')
			os.remove(f)
	arcpy.AddMessage('#################')
	arcpy.AddMessage(' ')