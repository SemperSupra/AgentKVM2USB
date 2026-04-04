import hid

def probe_features():
    vid = 0x2b77
    pid = 0x3661
    
    sys_dev = None
    devices = hid.enumerate(vid, pid)
    for d in devices:
        if d.get('usage', 0) == 0x104:
            try:
                sys_dev = hid.device()
                sys_dev.open_path(d['path'])
                print("Connected to System/Config Endpoint (0x104).")
                break
            except Exception as e:
                print("Failed to open System Endpoint:", e)
                return

    if not sys_dev:
        print("System endpoint not found.")
        return

    print("Probing GET_FEATURE_REPORT IDs 0-15 with lengths 1-32...")
    for report_id in range(16):
        found = False
        for length in range(1, 33):
            try:
                data = sys_dev.get_feature_report(report_id, length)
                if data:
                    hex_data = " ".join(f"{b:02X}" for b in data)
                    print(f"Report ID {report_id:02X} -> Length: {len(data)}, Data: {hex_data}")
                    found = True
                    break # Stop looking for other lengths for this ID
            except Exception as e:
                pass
        if not found:
            pass
            
    sys_dev.close()

if __name__ == "__main__":
    probe_features()
