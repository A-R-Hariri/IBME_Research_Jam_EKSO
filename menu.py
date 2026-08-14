import time
import config

from dataport import add_cmd,CMD_get_time,CMD_get_date,CMD_DataLogger
from dataport import CMD_get_settings,CMD_get_feedback,CMD_set_value,CMD_cancel_action,CMD_request_action,CMD_get_state_data,CMD_get_step_ready_status

MNU_MAIN = 0
MNU_COM_SETUP = 1
MNU_SEND_CMD = 2
MNU_READ_DATA = 3

menuID = MNU_MAIN

def run_menu(conn, inStr, bRefreshDisplay):
    global menuID
    
    if inStr != '-': 
        if menuID == MNU_MAIN:
            if inStr == '0':
                config.bExit = True
                return
            elif inStr == '1':
                menuID = MNU_COM_SETUP
            elif inStr == '2':
                menuID = MNU_SEND_CMD
            elif inStr == '3':
                menuID = MNU_READ_DATA
        elif menuID == MNU_COM_SETUP:
            if inStr == '0':
                menuID = MNU_MAIN
        elif menuID == MNU_SEND_CMD:
            if inStr == '0':
                menuID = MNU_MAIN
            elif inStr == '1':
                conn.send([add_cmd,[CMD_get_time,[None]]])
                time.sleep(0.25)
            elif inStr == '2':
                conn.send([add_cmd,[CMD_get_date,[None]]])
                time.sleep(0.25)
            elif inStr == '3':
                conn.send([add_cmd,[CMD_get_settings,[None]]])
                time.sleep(0.25)
            elif inStr == '4':
                conn.send([add_cmd,[CMD_get_feedback,[None]]])
                time.sleep(0.25)
            elif inStr == '5':
                # get the parameter ID
                ID = int(input("Enter ID (200 - 219): "))

                # get the new value
                fVal = float(input("Enter value: "))

                conn.send([add_cmd,[CMD_set_value,[ID,fVal]]])
                time.sleep(0.25)
            elif inStr == '6':
                conn.send([add_cmd,[CMD_cancel_action,[None]]])
                time.sleep(0.25)
            elif inStr == '7':
                conn.send([add_cmd,[CMD_request_action,['walk']]])
                time.sleep(0.25)
            elif inStr == '8':
                conn.send([add_cmd,[CMD_get_state_data,[None]]])
                time.sleep(0.25)
            elif inStr == '9':
                conn.send([add_cmd,[CMD_get_step_ready_status,[None]]])
                time.sleep(0.25)
        elif menuID == MNU_READ_DATA:
            if inStr == '0':
                menuID = MNU_MAIN
            if inStr == '1':
                conn.send([add_cmd,[CMD_DataLogger,['start']]])
                print ("DataLogging: ON")
            if inStr == '2':
                conn.send([add_cmd,[CMD_DataLogger,['stop']]])
                print ("DataLogging: OFF")
            if inStr == '3':
                conn.send([add_cmd,[CMD_DataLogger,['start_read_push']]])
                print ("Push DataLogging: ON")
            if inStr == '4':
                conn.send([add_cmd,[CMD_DataLogger,['stop_read_push']]])
                print ("Push DataLogging: OFF")

    if bRefreshDisplay:
        
        if menuID == MNU_MAIN:
            print ("\nMain Menu")
            print ("1> COM Setup")
            print ("2> Send Commands")
            print ("3> Read Data")
            print ("0> Exit")
        elif menuID == MNU_COM_SETUP:
            print ("COM Setup")
            print ("1> Display COM ports")
            print ("0> Back")
        elif menuID == MNU_SEND_CMD:
            print ("Send Commands")
            print ("1> Get Time")
            print ("2> Get Date")
            print ("3> Get Settings")
            print ("4> Get Feedback")
            print ("5> Set Value")
            print ("6> Cancel Action")
            print ("7> Walk (take step)")
            print ("8> Get State Data")
            print ("9> Get Step Ready")
            print ("0> Back")
        elif menuID == MNU_READ_DATA:
            print ("Read Data")
            print ("1> Start Data Stream")
            print ("2> Stop Data Stream")
            print ("3> Start Push Data")
            print ("4> Stop Push Data")
            print ("0> Back")
