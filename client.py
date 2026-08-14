import time
from multiprocessing.connection import Client
from dataport import add_cmd
from dataport import CMD_DataLogger,CMD_get_time,CMD_get_date
from dataport import CMD_get_settings,CMD_get_feedback,CMD_set_value,CMD_cancel_action

from serial_port import CMD_SerialPort

conn = Client(('localhost', 6000), authkey=b'secret password')

portName = 'COM14'
#portName = '/dev/ttyACM0'

# open the port
conn.send([CMD_SerialPort, ['open', portName]])
conn.send([CMD_DataLogger, ['open', 'ekso_data.csv']])
time.sleep(1)

# sample commands
conn.send([add_cmd,[CMD_get_time,[None]]])
conn.send([add_cmd,[CMD_get_date,[None]]])

# start/stop data logging
conn.send([add_cmd,[CMD_DataLogger,['start']]])
time.sleep(2)
conn.send([add_cmd,[CMD_DataLogger,['stop']]])

conn.send([add_cmd,[CMD_set_value,[200,13]]])
conn.send([add_cmd,[CMD_set_value,[202,15.5]]])

# close the port
conn.send([CMD_DataLogger, ['close', None]])
conn.send([CMD_SerialPort, ['close',None]])

# kill the server process
conn.send('close_server')

# close this connection
conn.close()
