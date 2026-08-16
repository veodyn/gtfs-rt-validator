// Prints the 0.0.4 bindings' own descriptor as flat lines, so the Python side
// needs no protobuf library to read it. Asking the artifact rather than reading
// a .proto of that era removes a guess about which revision it was built from.
//
// Run through JDK 17's single-file source launcher, no compile step:
//   java -cp <bindings.jar>:<protobuf-java.jar> tools/DumpDescriptor.java
//
// Line format, tab separated, one record per line:
//   M  <qualified message name>
//   E  <qualified enum name>
//   V  <qualified enum name>  <value name>  <value number>  <deprecated>
//   F  <owner>  <number>  <name>  <type>  <label>  <target>  <D|->  <default>  <deprecated>
//
// The eighth field column is the reason this format is not the obvious one. A
// repeated or message-kind field has no default at all (protobuf-java's
// getDefaultValue() throws for those), while sixteen string fields have the
// empty string as their default. Both would print as an empty last column, so
// "" cannot mean both. The flag column says which: `D` means column nine holds
// the effective default and may legitimately be empty, `-` means no default
// applies and column nine is padding. Without it the string fields would
// silently generate as default=None.
//
// "Effective", not "declared": getDefaultValue() is called unconditionally for
// every singular non-message field, never gated on hasDefaultValue(). The jar
// answers SCHEDULED for TripDescriptor.schedule_relationship even though that
// field declares no default, and SCHEDULED is what upstream's rules see.
import com.google.protobuf.Descriptors;

public class DumpDescriptor {
    public static void main(String[] args) {
        for (Descriptors.Descriptor d :
                com.google.transit.realtime.GtfsRealtime.getDescriptor().getMessageTypes()) {
            emitMessage(d, "");
        }
    }

    private static void emitMessage(Descriptors.Descriptor d, String prefix) {
        String name = prefix.isEmpty() ? d.getName() : prefix + "." + d.getName();
        System.out.println("M\t" + name);
        for (Descriptors.FieldDescriptor f : d.getFields()) {
            String type = f.getType().name().toLowerCase();
            String target = "";
            if (type.equals("message")) target = f.getMessageType().getFullName();
            if (type.equals("enum")) target = f.getEnumType().getFullName();
            String label = f.isRequired() ? "required" : f.isRepeated() ? "repeated" : "optional";

            boolean applies = !f.isRepeated() && !type.equals("message");
            String flag = applies ? "D" : "-";
            String def = applies ? renderDefault(f, type) : "";
            if (def.indexOf('\t') >= 0 || def.indexOf('\n') >= 0) {
                throw new IllegalStateException(
                    "default of " + name + "." + f.getName() + " contains a separator; "
                    + "the flat format cannot carry it");
            }
            System.out.println(
                "F\t" + name + "\t" + f.getNumber() + "\t" + f.getName() + "\t"
                + type + "\t" + label + "\t" + target + "\t" + flag + "\t" + def
                + "\t" + f.getOptions().getDeprecated());
        }
        for (Descriptors.EnumDescriptor e : d.getEnumTypes()) {
            System.out.println("E\t" + name + "." + e.getName());
            for (Descriptors.EnumValueDescriptor v : e.getValues()) {
                // The fifth column is asked of every member so that "this
                // artifact deprecates none" is a measured answer rather than an
                // absence. The current .proto deprecates one enum member and
                // the 0.0.4 descriptor predates it, so this prints false
                // throughout today; a later pin is what it exists for.
                System.out.println("V\t" + name + "." + e.getName() + "\t"
                    + v.getName() + "\t" + v.getNumber()
                    + "\t" + v.getOptions().getDeprecated());
            }
        }
        for (Descriptors.Descriptor nested : d.getNestedTypes()) {
            emitMessage(nested, name);
        }
    }

    private static String renderDefault(Descriptors.FieldDescriptor f, String type) {
        Object value = f.getDefaultValue();
        // An enum default stringifies to its value name, which the Python side
        // maps through the enum table this same dump emits. Named explicitly
        // rather than left to toString(), so the contract is visible here.
        if (type.equals("enum")) {
            return ((Descriptors.EnumValueDescriptor) value).getName();
        }
        // The 0.0.4 descriptor declares no bytes field, so a ByteString would
        // need a rendering nobody has had to design. Fail rather than emit
        // ByteString.toString(), which is a debug form, not a value.
        if (type.equals("bytes")) {
            throw new IllegalStateException(
                "bytes field " + f.getFullName() + " needs a ByteString rendering");
        }
        return String.valueOf(value);
    }
}
