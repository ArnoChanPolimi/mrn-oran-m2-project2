import src.e2ap_xapp as e2ap_xapp
#from ran_messages_pb2 import *
from time import sleep
from ricxappframe.e2ap.asn1 import IndicationMsg
import argparse

import sys
sys.path.append("oai-oran-protolib/builds/")
from ran_messages_pb2 import *


def parse_args():
    parser = argparse.ArgumentParser(description="Project 2 BER-based DL MCS control xApp")
    parser.add_argument("--ber-threshold", type=float, default=0.10,
                        help="BER threshold used by the control loop")
    parser.add_argument("--target-low-mcs", type=int, default=4,
                        help="DL MCS forced when the BER condition is triggered")
    parser.add_argument("--normal-mcs", type=int, default=20,
                        help="DL MCS requested when the UE returns to normal operation")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="Monitoring interval in seconds")
    parser.add_argument("--trigger", choices=["below", "above"], default="below",
                        help="Trigger low MCS when BER is below or above the threshold")
    return parser.parse_args()


def xappLogic(args):

    # instanciate xapp 
    connector = e2ap_xapp.e2apXapp()
    print("Project 2 control parameters:")
    print("  BER threshold: {}".format(args.ber_threshold))
    print("  target low DL MCS: {}".format(args.target_low_mcs))
    print("  normal DL MCS: {}".format(args.normal_mcs))
    print("  xApp polling interval: {}s".format(args.interval))
    print("  trigger condition: BER {} threshold".format(args.trigger))
    print("---------")

    # get gnbs connected to RIC
    gnb_id_list = connector.get_gnb_id_list()
    print("{} gNB connected to RIC, listing:".format(len(gnb_id_list)))
    for gnb_id in gnb_id_list:
        print(gnb_id)
    print("---------")

    # subscription requests
    for gnb in gnb_id_list:
        e2sm_buffer = e2sm_report_request_buffer()
        connector.send_e2ap_sub_request(e2sm_buffer,gnb)
        #connector.send_e2ap_control_request(e2sm_buffer,gnb)
    
    # read loop
    while True:
        sleep(args.interval)
        messgs = connector.get_queued_rx_message()
        if len(messgs) == 0:
            print("Monitoring tick: no new RIC indication in the last {}s".format(args.interval))
        else:
            print("{} messages received while waiting, printing:".format(len(messgs)))
            for msg in messgs:
                if msg["message type"] == connector.RIC_IND_RMR_ID:
                    print("RIC Indication received from gNB {}, decoding E2SM payload".format(msg["meid"]))
                    resp = decode_indication_response(msg["payload"])
                    process_indication_response(connector, msg["meid"], resp, args)
                else:
                    print("Unrecognized E2AP message received from gNB {}".format(msg["meid"]))


def decode_indication_response(payload):
    indm = IndicationMsg()
    indm.decode(payload)
    resp = RAN_indication_response()
    resp.ParseFromString(indm.indication_message)
    return resp


def process_indication_response(connector, meid, resp, args):
    ue_list = get_ue_list(resp)
    if ue_list is None:
        print("Indication response does not contain UE_LIST")
        print("___")
        return

    updates = []
    for ue in ue_list.ue_info:
        if not ue.HasField("dl_ber"):
            print("UE {} has no dl_ber field, skipping".format(ue.rnti))
            continue

        ber = ue.dl_ber
        current_mcs = ue.dl_mcs if ue.HasField("dl_mcs") else None
        current_target = ue.target_dl_mcs if ue.HasField("target_dl_mcs") else None
        force_low = should_force_low_mcs(ber, args)
        desired_mcs = args.target_low_mcs if force_low else args.normal_mcs
        state = "FORCE_LOW_MCS" if force_low else "NORMAL_OPERATION"

        print("UE {}: dl_ber={:.4f}, dl_mcs={}, target_dl_mcs={}, decision={}".format(
            ue.rnti, ber, current_mcs, current_target, state))

        if current_target != desired_mcs:
            updates.append((ue.rnti, desired_mcs))

    if updates:
        control_buf = e2sm_control_request_buffer(updates)
        connector.send_e2ap_control_request(control_buf, meid_to_string(meid))
        print("Sent control request with {} UE MCS update(s)".format(len(updates)))
    else:
        print("No MCS update needed")
    print("___")


def get_ue_list(resp):
    for entry in resp.param_map:
        if entry.key == RAN_parameter.UE_LIST and entry.HasField("ue_list"):
            return entry.ue_list
    return None


def should_force_low_mcs(ber, args):
    # The course project text asks to force low MCS when BER is below the threshold.
    if args.trigger == "below":
        return ber < args.ber_threshold
    return ber > args.ber_threshold


def meid_to_string(meid):
    if isinstance(meid, bytes):
        return meid.decode("ascii")
    return str(meid)


def e2sm_report_request_buffer():
    master_mess = RAN_message()
    master_mess.msg_type = RAN_message_type.INDICATION_REQUEST
    inner_mess = RAN_indication_request()
    inner_mess.target_params.extend([RAN_parameter.GNB_ID, RAN_parameter.UE_LIST])
    master_mess.ran_indication_request.CopyFrom(inner_mess)
    buf = master_mess.SerializeToString()
    return buf


def e2sm_control_request_buffer(mcs_updates):
    master_mess = RAN_message()
    master_mess.msg_type = RAN_message_type.CONTROL

    target_entry = master_mess.ran_control_request.target_param_map.add()
    target_entry.key = RAN_parameter.UE_LIST
    target_entry.ue_list.connected_ues = len(mcs_updates)

    for rnti, target_mcs in mcs_updates:
        ue = target_entry.ue_list.ue_info.add()
        ue.rnti = rnti
        ue.target_dl_mcs = target_mcs

    return master_mess.SerializeToString()


if __name__ == "__main__":
    xappLogic(parse_args())
