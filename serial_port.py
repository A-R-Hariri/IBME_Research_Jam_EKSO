import time
import serial
import serial.tools.list_ports
import binascii
import crcmod.predefined
from struct import *
from datetime import datetime
from datetime import timedelta

msgID = 200
ser = serial.Serial()

totalRxBytes = 0
totalTxBytes = 0

SIZE_HDR = 4
SIZE_CRC = 2

def CMD_SerialPort(data):
    global ser
    cmd = data[0]
    arg = data[1]
    
    if cmd == 'select':
        # this should only be called on the client side, not the server
        port_list = serial.tools.list_ports.comports()
        i = 1
        comName = []
        for p in port_list:
            comName.append(p.device)
            print (str(i) + "> " + p.device)
            i = i + 1
        else:
            print ("0> Exit")
            
        print ("Select a COM port")
        inStr = input(">> ")
        idx = int(inStr)
        idx = idx - 1
        return comName[idx]
    elif cmd == 'open':
        ser.port = arg
        ser.baudrate = 115200
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.bytesize = serial.EIGHTBITS
        ser.write_timeout = 0
        ser.timeout = 2
        ser.rtscts = False
        ser.xonxoff = False
        ser.open()
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ''
    elif cmd == 'close':
        ser.close()
        return ''       	

def send_cmd(cmd, numTxBytes, numRxBytes, data):
    """
    send a msg with the specified command and data, and return the msg response

    :param cmd: send this command in the message
    :param numTxBytes: send this number of bytes after the command
    :param numRxBytes: read this number of bytes in the response
    :param data: buffer of data to send
    :return: [readstatus (True/False), buffer of read data]
    """
    
    global msgID
    global ser
    global totalRxBytes
    global totalTxBytes
    global SIZE_HDR
    global SIZE_CRC

    end_time = datetime.now() + timedelta(milliseconds=500)

    # build the header
    txBuf = bytearray(SIZE_HDR+numTxBytes)
    txBuf[0] = cmd
    txBuf[1] = numTxBytes
    txBuf[2] = (msgID >> 8) & 255
    txBuf[3] = msgID & 255
    
    for i in range(numTxBytes):
        txBuf[i+SIZE_HDR] = data[i]
        
    calcCrc = get_crc(txBuf)
    
    txBuf.append(calcCrc >> 8)
    txBuf.append(calcCrc & 255)

# uncomment this to debug tx message data
#    for i in range(len(txBuf)):
#        print ("byte" + str(i) + " - " + str(txBuf[i]))

    # send the message
    try:
        ser.write(txBuf)
    except:
        print ("Timeout error in ser.write")
        print ("TxBytes=" + str(totalTxBytes) + ", RxBytes=" + str(totalRxBytes))
        return False, 0
    
    totalTxBytes += (numTxBytes+6)

    msgID = msgID + 1

    # read the response back
    rxSize = SIZE_HDR + numRxBytes + SIZE_CRC
    
    while True:
        try:
            bytesAvailable = ser.in_waiting
            if bytesAvailable >= rxSize:
                break
        except:
            print ("Error in ser wait")
            print ("TxBytes=" + str(totalTxBytes) + ", RxBytes=" + str(totalRxBytes))
            return False, 0

        if datetime.now() > end_time:
            # no full response in xx msecs, exit now
            lastMsgID = msgID - 1
            print ("*** MsgID=" + f"0x{lastMsgID:04x}" + ", Cmd=" + str(cmd) + ", timeout, Tx/Rx=" + str(totalTxBytes) + " / " + str(totalRxBytes) + ", Avail:" + str(bytesAvailable) + ", Exp: " + str(rxSize))
            
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            return False, 0
        
    try:
        rxBuf = ser.read(rxSize)
    except:
        print ("Read error, rxSize=" + str(rxSize))
        print ("TxBytes=" + str(totalTxBytes) + ", RxBytes=" + str(totalRxBytes))
        return False, 0

    totalRxBytes += rxSize

    # check CRC
    calcCrc = get_crc(rxBuf[0:rxSize-SIZE_CRC])
    r = unpack('>H',rxBuf[rxSize-SIZE_CRC:rxSize])
    readCrc = r[0]
    
    bReadGood = calcCrc == readCrc
    if not bReadGood:
        print ("CRC error on response: read=" + hex(readCrc) + ", calc=" + hex(calcCrc))
        for i in range(rxSize):
            print (str(i) + ": " + f"0x{rxBuf[i]:02x}")

        ser.reset_input_buffer()
        ser.reset_output_buffer()

    return bReadGood, rxBuf[SIZE_HDR:SIZE_HDR+numRxBytes]

def read_data(numRxBytes):
    """
    read the specified number of bytes from the open serial port ser

    :param numRxBytes: number of bytes to read
    :return: [readstatus (True/False), buffer of read data]
    """
    global ser
    global totalTxBytes
    global totalRxBytes
    global SIZE_HDR
    global SIZE_CRC

    end_time = datetime.now() + timedelta(seconds=5)

    # calculate total expected Rx msg size
    rxSize = SIZE_HDR + numRxBytes + SIZE_CRC
    
    while True:
        try:
            bytesAvailable = ser.in_waiting
            if bytesAvailable >= rxSize:
                break
        except:
            print ("Error in ser wait")
            print ("TxBytes=" + str(totalTxBytes) + ", RxBytes=" + str(totalRxBytes))
            return False, 0

        if datetime.now() > end_time:
            # no full response in xx msecs, exit now
            print ("*** timeout, Tx/Rx=" + str(totalTxBytes) + " / " + str(totalRxBytes) + ", Avail:" + str(bytesAvailable) + ", Exp: " + str(rxSize))
            
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            return False, 0
        
    try:
        rxBuf = ser.read(rxSize)
    except:
        print ("Read error, rxSize=" + str(rxSize))
        print ("TxBytes=" + str(totalTxBytes) + ", RxBytes=" + str(totalRxBytes))
        return False, 0

    totalRxBytes += rxSize

    # check CRC
    calcCrc = get_crc(rxBuf[0:rxSize-SIZE_CRC])
    r = unpack('>H',rxBuf[rxSize-SIZE_CRC:rxSize])
    readCrc = r[0]
    
    bReadGood = calcCrc == readCrc
    if not bReadGood:
        print ("CRC error on response: read=" + hex(readCrc) + ", calc=" + hex(calcCrc))
        for i in range(rxSize):
            print (str(i) + ": " + f"0x{rxBuf[i]:02x}")

        ser.reset_input_buffer()
        ser.reset_output_buffer()

    return bReadGood, rxBuf[SIZE_HDR:SIZE_HDR+numRxBytes]

def get_crc(data):
    crc16 = crcmod.predefined.mkCrcFun('crc-ccitt-false')
    digest = crc16(data)
    return digest

    