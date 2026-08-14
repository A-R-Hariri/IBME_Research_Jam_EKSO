import time
import config
import queue
from struct import *

from multiprocessing.connection import Client
from serial_port import CMD_SerialPort, send_cmd, read_data

# commands
CMD_GET_TIME = 150
CMD_GET_DATE = 151
CMD_GET_SETTINGS = 152
CMD_GET_DATA = 153
CMD_GET_FEEDBACK = 154
CMD_SET_VALUE = 155
CMD_CANCEL_ACTION = 156
CMD_REQUEST_ACTION = 157
CMD_GET_STATE_DATA = 158
CMD_GET_STEP_READY_STATUS = 159
CMD_PUSH_DATA = 160

ACTION_NONE = 0
ACTION_WALK = 1
ACTION_STAND = 2
ACTION_SIT = 3
ACTION_PAUSE = 4

q = queue.Queue()
fh_a = 0

DATA_LOGGING_PERIOD_MSEC = 20 
PUSH_DATA_READ_MSEC = 50

datalog_cmd_good = 0
datalog_cmd_total = 1

nextDataLogTime = 0
nextReadPushDataTime = 0

def add_cmd(f):
    q.put(f)

def run_serial_cmd():
    if not q.empty():
        f = q.get()
        func = f[0]
        args = f[1]
        func(args)
        q.task_done()

def run_log_data_stream():
    global nextDataLogTime

    timeNow_msec = time.time_ns() / 1000000

    # is it time for the next data request
    if config.bDataLogging and timeNow_msec >= nextDataLogTime:
        nextDataLogTime = timeNow_msec + DATA_LOGGING_PERIOD_MSEC
        add_cmd([CMD_get_datalog,[None]])
            
def run_log_push_data():
    global nextReadPushDataTime
    
    timeNow_msec = time.time_ns() / 1000000

    # is it time for the next push data read
    # note - this read will block until bytes are read or timeout
    # this should not be run in parallel with data logging
    if config.bReadPushData and timeNow_msec >= nextReadPushDataTime:
        nextReadPushDataTime = timeNow_msec + PUSH_DATA_READ_MSEC
        success, data = read_data(2)

        if success:
            print ((str(data[0]) + ", " + str(data[1])))


def CMD_get_datalog(args):
    global fh_a
    global datalog_cmd_good
    global datalog_cmd_total
    
    success, data = send_cmd(CMD_GET_DATA,0,54,0)
    datalog_cmd_total += 1

    if success:
        datalog_cmd_good += 1
        # create CSV string from data values
        strData = ""
        for i in range(27):
            strData += str(int(data[2*i]*256 + data[2*i+1])) + ","

        strData += "\n"
        fh_a.write(strData)
                   
def CMD_get_time(args):
    success, data = send_cmd(CMD_GET_TIME,0,4,0)

    if success:
        print ((str(data[0])+":"+str(data[1])+":"+str(data[2])))
  
def CMD_get_date(args):
    success, data = send_cmd(CMD_GET_DATE,0,4,0)

    if success:
        print ((str(data[1])+"/"+str(data[2])+"/"+str(data[0])))

def CMD_get_settings(args):
    success, data = send_cmd(CMD_GET_SETTINGS,0,44,0)
    
    strStandModes = ["Manual Lean","Auto Lean"]
    strSitModes = ["Min Lean","Normal Lean"]
    strWalkModes = ["First Step","ActiveStep","ProStep","ProStep+"]
    strTargetSounds = ["Off","Forward","Lateral","Both"]
    strLeanAllowance = ["Min","Max","Off"]
    strInjuryMode = ["Bilateral","Right Affected","Left Affected","2Free"]
    strSwingAssist = ["Adapt","Max","High Resist","Low Resist","Neutral","Low Assist","High Assist"]
    strStanceSupport = ["Low","Medium","High","Very High","Flex","Full"]
    strSwingComplete = ["2.5","2.0","1.5","1.0","0.5","0.3","0.1"]
    
    if success:
        for i in range(22):
            r = unpack('>H',data[2*i:2*(i+1)])
            fVal = float(r[0])

            if i == 0:
                print ("Upper Leg Length: "+str(fVal/100))
            elif i == 1:
                print ("Lower Leg Length: "+str(fVal/100))
            elif i == 2:
                print ("Step Length: "+str(fVal/100))
            elif i == 3:
                print ("Step Height: "+str(fVal/100))
            elif i == 4:
                print ("Swing Time: "+str(fVal/100))
            elif i == 5:
                print ("Stand Time: "+str(fVal/100))
            elif i == 6:
                print ("Knee Flex: "+str(fVal/100))
            elif i == 7:
                print ("Hip Flex: "+str(fVal/100))
            elif i == 8:
                iVal = int(fVal)
                if iVal > 32767:
                    iVal = iVal - 65535
                print ("Forward Shift: "+str(int(round(iVal/100,0))))
            elif i == 9:
                iVal = int(fVal)
                if iVal > 32767:
                    iVal = iVal - 65535
                print ("Lateral Shift: "+str(int(round(iVal/100,0))))
            elif i == 10:
                # print ("Walk Mode: "+strWalkModes[int(fVal)])
                print ("Walk Mode: ")
            elif i == 11:
                # print ("Stand Mode: "+strStandModes[int(fVal)])
                print ("Stand Mode: ")
            elif i == 12:
                print ("Target Sounds: "+strTargetSounds[int(fVal)])
            elif i == 13:
                print ("Injury Mode: "+strInjuryMode[int(fVal)])
            elif i == 14:
                strOut = "Left Swing Assist: "
                val = int(fVal)
                if val <= 20:
                    strOut = strOut + str(val*5)
                else:
                    strOut = strOut + strSwingAssist[val-21]
                print (strOut)
            elif i == 15:
                strOut = "Right Swing Assist: "
                val = int(fVal)
                if val <= 20:
                    strOut = strOut + str(val*5)
                else:
                    strOut = strOut + strSwingAssist[val-21]
                print (strOut)
            elif i == 16:
                print ("Left Stance Support: "+strStanceSupport[int(fVal)])
            elif i == 17:
                print ("Right Stance Support: "+strStanceSupport[int(fVal)])
            elif i == 18:
                # print ("Swing Complete: "+strSwingComplete[int(fVal)])
                print ("Swing Complete: ")
            elif i == 19:
                print ("PilotID: "+str(int(fVal)))
            elif i == 20:
                # print ("Sit Mode: "+strSitModes[int(fVal)])
                print ("Sit Mode: ")
            elif i == 21:
                # print ("Lean Allowance: "+strLeanAllowance[int(fVal)])
                print ("Lean Allowance: ")
        
def CMD_get_feedback(args):
    success, data = send_cmd(CMD_GET_FEEDBACK,0,34,0)
    
    if success:
        for i in range(15):
            r = unpack('>H',data[2*i:2*(i+1)])
            fVal = float(r[0])
            if fVal > 32767:
                fVal -= 65536
            if i == 0:
                print("Steps: " + str(int(fVal)))
            elif i == 1:
                print("Upright Time(sec): " + str(int(fVal)))
            elif i == 2:
                print("Walk Time(sec): " + str(int(fVal)))
            elif i == 3:
                print("MinGain, Left: " + str(fVal/10))
            elif i == 4:
                print("FwdGain, Left: " + str(fVal/10))
            elif i == 5:
                print("MinGain, Right: " + str(fVal/10))
            elif i == 6:
                print("FwdGain, Right: " + str(fVal/10))
            elif i == 7:
                print("Hip Stance Support, Left: " + str(fVal/10))
            elif i == 8:
                print("Knee Stance Support, Left: " + str(fVal/10))
            elif i == 9:
                print("Hip Stance Support, Right: " + str(fVal/10))
            elif i == 10:
                print("Knee Stance Support, Right: " + str(fVal/10))
            elif i == 11:
                print("Step Length, Left: " + str(fVal/10))
            elif i == 12:
                print("Step Length, Right: " + str(fVal/10))
            elif i == 13:
                print("Swing Time, Left: " + str(fVal/10))
            elif i == 14:
                print("Swing Time, Right: " + str(fVal/10))

        # rebuild time value
        tmHi = unpack('>H',data[30:32])
        tmLo = unpack('>H',data[32:34])
        Tsec = (float(tmHi[0])*65536.0 + float(tmLo[0])) / 1000
        print ("T="+str(Tsec)+" sec")

def CMD_set_value(args):
    data_out = bytearray(4)

    ID = args[0]
    fVal = args[1]
     
    if (ID <= 209):
        val = int(100.0 * fVal)
    else:
        val = int(fVal)
        
    data_out[0] = 0
    data_out[1] = ID
    data_out[2] = int(val / 256)
    data_out[3] = val % 256
    
    success, data_in = send_cmd(CMD_SET_VALUE,4,2,data_out)
    if success:
        if data_in[1] == 1:
            print("Error in CMD_set_value: Ekso State=" + str(data_in[0]))
        elif data_in[1] == 2:
            print("Error in CMD_set_value: Out of Range: ID=" + str(data_out[1]) + ", val=" + str(fVal))
        elif data_in[1] == 3:
            print("Error in CMD_set_value: value not allowed="  + str(fVal))
        elif data_in[1] != 0:
            print("Error, data_in[1]="+str(data_in[1]))
    else:
        print ("Error in CMD_set_value: ID=" + str(data_out[1]) + ", val=" + str(val))

def CMD_request_action(args):
    data_out = bytearray(2)

    action = args[0]

    if (action == 'walk'):
        data_out[0] = 0
        data_out[1] = ACTION_WALK
    
    success, data_in = send_cmd(CMD_REQUEST_ACTION,2,2,data_out)
    if success:
        if data_in[1] != 0:
            print("Error, data_in[1]="+str(data_in[1]))
    else:
        print ("Error in CMD_request_action: action=" + action)

def CMD_cancel_action(args):
    data_out = bytearray(2)
    data_out[0] = 1
    data_out[1] = 0
    
    success, data_in = send_cmd(CMD_CANCEL_ACTION,2,2,data_out)
    if success:
        if data_in[1] == 1:
            print("Error in CMD_cancel_action: Ekso State=" + str(data_in[0]))
        elif data_in[1] == 3:
            print("Error in CMD_cancel_action: Cmd not allowed")
    else:
        print ("Error in CMD_cancel_action: ID=" + str(data_out[1]))

def CMD_get_state_data(args):
    success, data_in = send_cmd(CMD_GET_STATE_DATA,0,6,0)
    if success:
        state = data_in[0]*256 + data_in[1]
        substate = data_in[2]*256 + data_in[3]
        flags = data_in[4]*256 + data_in[5]
        print(f"State Data Read OK.  state={state}, substate={substate}, flags={flags}")
    else:
        print(f"State Data Read NOT OK. Code={data_in[0]}")

def CMD_get_step_ready_status(args):
    success, data_in = send_cmd(CMD_GET_STEP_READY_STATUS,0,2,0)
    if success:
        status = data_in[0]*256 + data_in[1]
        print(f"Step Ready Status Read OK.  status={status}")
    else:
        print(f"Step Ready Status Read NOT OK. Code={data_in[0]}")


def CMD_DataLogger(args):
    global fh_a
 
    cmd = args[0]
    if cmd == 'start':
        config.bDataLogging = True
    elif cmd == 'stop':
        config.bDataLogging = False
    elif cmd == 'open':
        fName = args[1]
        fh_a = open(fName, "a", buffering=1)
    elif cmd == 'close':
        fh_a.close()
    elif cmd == 'start_read_push':
        config.bReadPushData = True
    elif cmd == 'stop_read_push':
        config.bReadPushData = False
