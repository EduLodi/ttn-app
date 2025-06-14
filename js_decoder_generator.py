import json
import argparse
import struct
import os

# This dictionary is the core of the translation. It maps Python struct
# format characters to JavaScript DataView methods, their byte size,
# and whether they return a BigInt (for 64-bit integers).
PACKER_MAP = {
    # Format: 'packer': ('dataViewMethod', byte_size, returns_bigint)
    'b': ('getInt8', struct.calcsize('b'), False),
    'B': ('getUint8', struct.calcsize('B'), False),
    'h': ('getInt16', struct.calcsize('h'), False),
    'H': ('getUint16', struct.calcsize('H'), False),
    'i': ('getInt32', struct.calcsize('i'), False),
    'I': ('getUint32', struct.calcsize('I'), False),
    'l': ('getInt32', struct.calcsize('l'), False),
    'L': ('getUint32', struct.calcsize('L'), False),
    'q': ('getBigInt64', struct.calcsize('q'), True),
    'Q': ('getBigUint64', struct.calcsize('Q'), True),
    'f': ('getFloat32', struct.calcsize('f'), False),
    'd': ('getFloat64', struct.calcsize('d'), False),
    # 's' for strings is handled as a special case
}

def generate_decoder_function(template_path: str) -> str:
    """
    Generates a TTN JavaScript decoder function from a payload_template.json file.

    Args:
        template_path: The path to the payload_template.json file.

    Returns:
        A string containing the complete JavaScript decodeUplink function.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found at: {template_path}")

    with open(template_path, 'r') as f:
        template = json.load(f)

    # Validate template
    if "_field_order" not in template or "fields" not in template:
        raise ValueError("Template must contain '_field_order' and 'fields' keys.")

    js_lines = []
    js_lines.append("function decodeUplink(input) {")
    js_lines.append("  // Decodes a binary payload into a structured object.")
    js_lines.append("  // Generated from template by Python script.")
    js_lines.append("")
    js_lines.append("  var data = {};")
    js_lines.append("  var offset = 0;")
    
    # *** FIX IS HERE ***
    # The input.bytes is an array of numbers, not a typed array.
    # We must first create a Uint8Array from it, then get its buffer.
    js_lines.append("  var buffer = Uint8Array.from(input.bytes).buffer;")
    js_lines.append("  var view = new DataView(buffer);")
    js_lines.append("")

    string_decoder_needed = False

    for field_name in template["_field_order"]:
        field_def = template["fields"].get(field_name)
        if not field_def:
            raise ValueError(f"Field '{field_name}' from '_field_order' is not defined in 'fields'.")
        
        js_lines.append(f"  // Field: {field_name}, Type: {field_def.get('type')}")
        
        packer = field_def.get("packer")
        
        if packer:
            # Handle standard numerical/struct types
            if packer in PACKER_MAP:
                method, byte_size, returns_bigint = PACKER_MAP[packer]
                
                # Determine endianness for multi-byte fields
                is_little_endian = "false"
                if byte_size > 1:
                    byte_order = field_def.get('byte_order', 'big')
                    is_little_endian = "true" if byte_order == 'little' else "false"
                    js_lines.append(f"  // {byte_size} bytes, {byte_order}-endian")
                else:
                    js_lines.append(f"  // {byte_size} byte")

                # Generate the line to read the data
                js_line = f"  data.{field_name} = view.{method}(offset, {is_little_endian});"
                if returns_bigint:
                    # BigInts are not directly serializable to JSON in some contexts,
                    # so converting to a string is the safest default.
                    js_line = js_line.replace(";", ".toString(); // Converted BigInt to string")

                js_lines.append(js_line)
                js_lines.append(f"  offset += {byte_size};")

            # Handle packed strings like "4s"
            elif packer.endswith('s'):
                try:
                    length = int(packer[:-1])
                    js_lines.append(f"  // {length} bytes, string")
                    js_lines.append(f"  data.{field_name} = bytesToString(input.bytes.slice(offset, offset + {length}));")
                    js_lines.append(f"  offset += {length};")
                    string_decoder_needed = True
                except ValueError:
                    raise ValueError(f"Invalid string packer format for field '{field_name}': '{packer}'")
            else:
                 raise ValueError(f"Unknown packer format for field '{field_name}': '{packer}'")

        elif field_def.get("type") == "string":
            # Handle non-packed strings that have a length property
            length = field_def.get('length')
            if not length:
                raise ValueError(f"String field '{field_name}' must have a 'length' property if no 'packer' is defined.")
            
            js_lines.append(f"  // {length} bytes, string")
            js_lines.append(f"  data.{field_name} = bytesToString(input.bytes.slice(offset, offset + {length}));")
            js_lines.append(f"  offset += {length};")
            string_decoder_needed = True
        
        elif field_def.get("type") == "hex_string":
            length_bytes = field_def.get('length_bytes')
            if not length_bytes:
                raise ValueError(f"hex_string field '{field_name}' must have a 'length_bytes' property.")
            js_lines.append(f"  // {length_bytes} bytes, hex string")
            js_lines.append(f"  // Note: Standard JS decoder does not have a simple bytesToHexString. This field will be raw bytes.")
            js_lines.append(f"  data.{field_name}_bytes = input.bytes.slice(offset, offset + {length_bytes});")
            js_lines.append(f"  offset += {length_bytes};")

        js_lines.append("")

    js_lines.append("  return {")
    js_lines.append("    data: data,")
    js_lines.append("    warnings: [],")
    js_lines.append("    errors: []")
    js_lines.append("  };")
    js_lines.append("}")
    
    # Prepend the string decoder helper function if it was used
    if string_decoder_needed:
        helper_function = [
            "// Helper function to decode a byte array to a UTF-8 string.",
            "function bytesToString(bytes) {",
            "  var result = \"\";",
            "  for (var i = 0; i < bytes.length; i++) {",
            "    result += String.fromCharCode(bytes[i]);",
            "  }",
            "  return result;",
            "}",
            ""
        ]
        js_lines = helper_function + js_lines

    return "\n".join(js_lines)

def main():
    """Main function to run the script from the command line."""
    parser = argparse.ArgumentParser(
        description="Generate a TTN JavaScript decoder function from a JSON payload template."
    )
    parser.add_argument(
        "template_file",
        help="Path to the input payload_template.json file."
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to the output .js file. If not provided, prints to console."
    )
    args = parser.parse_args()

    try:
        decoder_js = generate_decoder_function(args.template_file)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(decoder_js)
            print(f"Successfully generated decoder function and saved to '{args.output}'")
        else:
            print("\n--- Generated TTN Decoder Function ---\n")
            print(decoder_js)
            print("\n--- End of Function ---")

    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
