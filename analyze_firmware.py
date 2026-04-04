import sys
import string
import re

def extract_strings(filename, min_len=6):
    try:
        with open(filename, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return

    pattern = b'[%s]{%d,}' % (re.escape(bytes(string.printable, 'ascii')), min_len)
    strings = re.findall(pattern, data)
    unique_strings = set(s.decode('ascii', errors='ignore').strip() for s in strings)
    
    keywords = ['GET', 'SET', 'FEATURE', 'PROPERTY', 'HID', 'USB', 'EDID', 'VGA', 'DVI', 'KVM', 'MOUSE', 'KEYBOARD', 'CMD', 'CTRL', 'MACRO', 'FIRMWARE', 'UPDATE', 'LED', 'RESET', 'I2C']
    interesting = []
    
    for s in unique_strings:
        s_upper = s.upper()
        if any(kw in s_upper for kw in keywords):
            interesting.append(s)
            
    print(f"Found {len(interesting)} interesting strings in {filename}:")
    for s in sorted(interesting)[:100]:
        print(s)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_strings(sys.argv[1])
    else:
        print("Provide filename")
