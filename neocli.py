#!/usr/bin/env python3
import asyncio
import sys
import argparse
import json
import logging
import socket
import os
from neohub import NeoHub, NeoDevice
import paho.mqtt.client as mqttClient
import paho.mqtt.publish as publish
import time
import logging.handlers as handlers
from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
import jsonpickle
import mysql.connector


logger = logging.getLogger("Heatmiser-MQTT-Log")
logging.basicConfig(level=logging.WARN)

def setup_logger():
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    fileHandler = handlers.TimedRotatingFileHandler('heatmiser-mqtt.log', when='D', interval=1, backupCount=1)
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

def on_connect(client, userdata, flags, rc):
 
    if rc == 0:
 
        logger.debug("Connected to broker")

        global Connected                #Use global variable
        Connected = True                #Signal connection 
 
    else:
 
        logger.warning("Connection failed")

def on_message(client, userdata, msg):
    logger.info ("Message received: "  + msg.payload)
    payload = json.loads(msg.payload)


def ok(what):
    if what:
        return 0
    else:
        print(repr(what))
        return 1

async def main(neo, cmd, args):
    await neo.async_setup()

    if cmd == "call":
        print(json.dumps(await neo.call(json.loads(args[1])), sort_keys=True, indent=2))
        return 0

    if cmd == "stat":
        print(json.dumps((await neo.update())[args[1]], sort_keys=True, indent=2))
        return 0

    if cmd == "set_diff":
        return ok(await neo.set_diff(args[1], args[2]))

    if cmd == "switch_on":
        return (await neo.neoplugs()[args[1]].switch_on())

    if cmd == "switch_off":
        return (await neo.neoplugs()[args[1]].switch_off())

    if cmd == "script":
        p = neo.neoplugs()["F1 Hall Plug"]
        print(repr(p))
        await p.switch_off()
        print(repr(p))
        await p.switch_on()
        print(repr(p))

    if cmd == "rename_zone":
        return ok(await neo.zone_title(args[1], args[2]))

    if cmd == "remove_zone":
        return ok(await neo.remove_zone(args[1]))

    if cmd == "frost_on":
        return ok(await neo.frost_on(args[0]))

    if cmd == "frost_off":
        return ok(await neo.frost_off(args[0]))

    if cmd == "set_program_mode":
        return ok(await neo.set_program_mode(args[1]))

    if cmd == "list":
#         for name in neo.neostats():
#             ns = neo.neostats()[name]
#             print(repr(ns))
#         print("")
#         for name in neo.neoplugs():
#             ns = neo.neoplugs()[name]
#             print(repr(ns))
        return neo.neostats()

    if cmd == "list-stats":
        for name in neo.neostats():
            ns = neo.neostats()[name]
            print(repr(ns))
        return 0

    if cmd == "stat-names":
        for name in neo.neostats():
            print(name)
        return 0

    if cmd == "list-plugs":
        for name in neo.neoplugs():
            ns = neo.neoplugs()[name]
            print(repr(ns))
        return 0

    return 1



if __name__ == '__main__':
    
    setup_logger()
    
    parser = argparse.ArgumentParser()

    parser.add_argument('-b', '--broker', help='IP Address for MQTT Broker (Required)', required=True)
    parser.add_argument('-p', '--port', help='Port for MQTT Broker (Required)', required=True)
    parser.add_argument('-u', '--user', help='User for MQTT Broker (Required)', required=True)
    parser.add_argument('-pw', '--password', help='Password for MQTT Broker (Required)', required=True)
    parser.add_argument('-ni', '--neoip', help='Ip address for Neo Hub (Required)', required=True)
    parser.add_argument('-mh', '--mysqlhost', help='Ip address for MySQL (Required)', required=True)
    parser.add_argument('-md', '--mysqldb', help='Database for MySQL (Required)', required=True)
    parser.add_argument('-mu', '--mysqluser', help='User for MySQL (Required)', required=True)
    parser.add_argument('-mp', '--mysqlpass', help='Password for MySQL (Required)', required=True)
    
    args = vars(parser.parse_args())
    
    Connected = False #global variable for the state of the connection
     
    broker_address= args['broker']
    port = args['port']
    user = args['user']
    password = args['password'] 
    neoip = args['neoip']
    
    client = mqttClient.Client("Heatmiser")               #create new instance
    client.username_pw_set(user, password=password)    #set username and password
    client.on_connect= on_connect                      #attach function to callback
    client.on_message= on_message 
    client.connect(broker_address, int(port))  #connect to broker
    client.loop_start() 
    
    loop = asyncio.get_event_loop()
    neo = NeoHub(neoip, 4242)
    
    mydb = mysql.connector.connect(
      host=args['mysqlhost'],
      user=args['mysqluser'],
      passwd=args['mysqlpass'],
      database=args['mysqldb']
    )
    
    
    try:
        while True:
            #print('getting status')
            retval = loop.run_until_complete(main(neo, "list", args))
            mycursor = mydb.cursor()
            
            data = {}  
            for name in retval:
                ns = neo.neostats()[name]
                
                data[name] = []  
                data[name].append({  
                    'id': ns.id(),
                    'temperature': ns.current_temperature(),
                    'heating': ns.currently_heating(),
                    'frost': ns.is_frosted()
                })
                
                sql = "INSERT INTO readings (thermoid, name, temperature, heating, frost) VALUES (%s, %s, %s, %s, %s)"
                val = (ns.id(), name, ns.current_temperature(), ns.currently_heating(), ns.is_frosted())
                mycursor.execute(sql, val)
                
            jsonData = jsonpickle.encode(data)
            logger.info(jsonData)
            
            client.publish('heating/state',jsonData)
            mydb.commit()
            time.sleep(60)# sleep for 5 seconds before next call
     
    except KeyboardInterrupt:
        print ("exiting")
        client.disconnect()
        client.loop_stop()

    cmd = sys.argv[2]
    args = sys.argv[3:]
    retval = loop.run_until_complete(main(neo, cmd, args))
    loop.close()
    sys.exit(retval)


