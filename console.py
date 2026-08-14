import config
import KBHit
from multiprocessing.connection import Client
from serial_port import CMD_SerialPort
from dataport import CMD_DataLogger
from menu import run_menu

conn = Client(('localhost', 6000), authkey=b'secret password')

# select the COM port
portName = CMD_SerialPort(['select',''])
            
# open the requested COM port            
conn.send([CMD_SerialPort, ['open', portName]])
conn.send([CMD_DataLogger, ['open', 'ekso_data.csv']])

kb = KBHit.KBHit()

# main loop - run until exit flag is set
refresh = True
while not config.bExit:
    c = '-'
    if kb.kbhit():
        refresh = True
        
        c = kb.getch()
        if ord(c) == 27: # ESC
            break
        print(c)
        
    run_menu(conn, c, refresh)
    refresh = False
        
# restore normal terminal settings
kb.set_normal_term()

# close the serial connection
conn.send([CMD_SerialPort, ['close',None]])
conn.send([CMD_DataLogger, ['close', None]])

# kill the server
conn.send('close_server')

# close this connection
conn.close()

exit()
