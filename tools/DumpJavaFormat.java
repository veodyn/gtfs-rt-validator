/*
 * Oracle for src/gtfs_rt_validator/rules/_shared/javafmt.py.
 *
 * The ops listed under Input below are every Java rendering that reaches compat
 * occurrence text. This prints each of them for a corpus, so the Python side is
 * compared against a running JVM rather than against a hand-computed
 * expectation.
 *
 * The JVM matters and is not incidental. Float.toString and Double.toString were
 * rewritten in JDK 19 (JDK-4511638) to emit the shortest round-tripping decimal;
 * the jdk.internal.math.FloatingDecimal in JDK 17, which upstream's pom targets,
 * emits a longer string for a large class of values. Run this under 17, which is
 * what tools/diff_javafmt_against_java.py does through tools/jarenv.py.
 *
 * Run by tools/diff_javafmt_against_java.py. By hand:
 *   /path/to/jdk17/bin/java tools/DumpJavaFormat.java < cases.tsv
 *
 * Input, one case per line, tab separated: <id> <op> <arg>
 * Output, one line per case: <id> <op> <result...>, tab separated.
 *
 *   F32    <int bits, hex>   Float.toString(f)
 *   F64    <long bits, hex>  Double.toString(d)
 *   FMT2F  <int bits, hex>   String.format("%.2f", f), the float overload
 *   FMT2D  <long bits, hex>  String.format("%.2f", d), then the same in
 *                            Locale.ROOT, so a machine whose default locale
 *                            writes a comma shows up as two differing columns
 *                            instead of as a silent Python-side failure.
 *   LIST   <items>           java.util.Arrays.asList(...).toString(), items
 *                            separated by U+001F, an item of U+001E being null
 *   LISTI  <ints>            the same for List<Integer>, comma separated
 *   BOOL   <0|1>             "" + booleanValue
 *   NULL   <prefix>          prefix + (Object) null, the concatenation itself
 *   ENUMS  <ignored>         every protobuf enum constant reachable from
 *                            GtfsRealtime, as ENUM <Outer.Enum> <name> <number>,
 *                            one line each. Needs the bindings jar on the
 *                            classpath; prints ENUMS SKIPPED without it.
 *   LOCALE <ignored>         Locale.getDefault() and the JDK version, so the
 *                            Python side records what it measured against.
 *
 * Bit patterns rather than decimal literals: they name the exact value with no
 * parse step in between, which is the only way to put -0.0, a NaN with a
 * payload, and a subnormal into the corpus and know the JVM saw what Python
 * meant.
 */

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class DumpJavaFormat {

  private static final String ITEM_SEPARATOR = "\u001F";
  private static final String NULL_ITEM = "\u001E";

  public static void main(String[] args) throws Exception {
    BufferedReader in = new BufferedReader(new InputStreamReader(System.in, "UTF-8"));
    String line;
    while ((line = in.readLine()) != null) {
      if (line.trim().isEmpty()) {
        continue;
      }
      String[] f = line.split("\t", -1);
      String id = f[0];
      String op = f[1];
      String arg = f.length > 2 ? f[2] : "";
      try {
        run(id, op, arg);
      } catch (Exception e) {
        System.out.println(id + "\tERROR\t" + e.getClass().getName() + ": " + e.getMessage());
      }
    }
  }

  private static void run(String id, String op, String arg) {
    switch (op) {
      case "F32":
        System.out.println(id + "\tF32\t" + Float.toString(floatOf(arg)));
        break;
      case "F64":
        System.out.println(id + "\tF64\t" + Double.toString(doubleOf(arg)));
        break;
      case "FMT2F":
        // The float overload, to settle whether Formatter widens to double
        // before choosing digits. It does: Formatter.print(float) delegates to
        // print((double) value), so "%.2f" of 0.005f is not "%.2f" of 0.005.
        // A rule holding a protobuf float must therefore widen first.
        System.out.println(id + "\tFMT2F\t" + String.format("%.2f", floatOf(arg)));
        break;
      case "FMT2D": {
        double d = doubleOf(arg);
        System.out.println(
            id + "\tFMT2D\t" + String.format("%.2f", d)
                + "\t" + String.format(Locale.ROOT, "%.2f", d));
        break;
      }
      case "LIST":
        System.out.println(id + "\tLIST\t" + items(arg));
        break;
      case "LISTI":
        System.out.println(id + "\tLISTI\t" + integers(arg));
        break;
      case "BOOL":
        System.out.println(id + "\tBOOL\t" + ("" + arg.equals("1")));
        break;
      case "NULL":
        System.out.println(id + "\tNULL\t" + (arg + (Object) null));
        break;
      case "ENUMS":
        dumpEnums(id);
        break;
      case "LOCALE":
        System.out.println(
            id + "\tLOCALE\t" + Locale.getDefault() + "\t" + System.getProperty("java.version"));
        break;
      default:
        System.out.println(id + "\tERROR\tunknown op " + op);
    }
  }

  private static float floatOf(String hex) {
    return Float.intBitsToFloat((int) Long.parseLong(hex, 16));
  }

  private static double doubleOf(String hex) {
    return Double.longBitsToDouble(Long.parseUnsignedLong(hex, 16));
  }

  /** List&lt;String&gt;.toString(), with the NULL_ITEM sentinel standing for null. */
  private static String items(String arg) {
    List<String> out = new ArrayList<>();
    if (!arg.isEmpty()) {
      for (String part : arg.split(ITEM_SEPARATOR, -1)) {
        out.add(part.equals(NULL_ITEM) ? null : part);
      }
    }
    return out.toString();
  }

  private static String integers(String arg) {
    List<Integer> out = new ArrayList<>();
    if (!arg.isEmpty()) {
      for (String part : arg.split(",", -1)) {
        out.add(Integer.valueOf(part));
      }
    }
    return out.toString();
  }

  /**
   * Every enum constant under GtfsRealtime, as the protobuf bindings define it.
   *
   * An enum reaches occurrence text as its constant name, because upstream
   * concatenates the value into a string. That is Enum.toString(), which
   * protobuf's generated enums do not override, so it is name(). Printing both
   * would compare a thing against itself; what is worth measuring is that the
   * names and numbers agree with proto/schema_2015.py, which is what the Python
   * side asserts.
   */
  private static void dumpEnums(String id) {
    Class<?> outer;
    try {
      outer = Class.forName("com.google.transit.realtime.GtfsRealtime");
    } catch (ClassNotFoundException e) {
      System.out.println(id + "\tENUMS\tSKIPPED\tno gtfs-realtime bindings on the classpath");
      return;
    }
    for (Class<?> nested : allNested(outer)) {
      if (!nested.isEnum()) {
        continue;
      }
      String raw = nested.getName();
      String marker = "GtfsRealtime$";
      String name = raw.substring(raw.indexOf(marker) + marker.length()).replace('$', '.');
      for (Object constant : nested.getEnumConstants()) {
        Enum<?> value = (Enum<?>) constant;
        int number = number(value);
        if (number != Integer.MIN_VALUE) {
          System.out.println(id + "\tENUM\t" + name + "\t" + value.toString() + "\t" + number);
        }
      }
    }
  }

  private static List<Class<?>> allNested(Class<?> root) {
    List<Class<?>> out = new ArrayList<>();
    for (Class<?> nested : root.getDeclaredClasses()) {
      out.add(nested);
      out.addAll(allNested(nested));
    }
    return out;
  }

  /** getNumber(), or MIN_VALUE for the UNRECOGNIZED-style constants that throw. */
  private static int number(Enum<?> value) {
    try {
      return (Integer) value.getClass().getMethod("getNumber").invoke(value);
    } catch (Exception e) {
      return Integer.MIN_VALUE;
    }
  }
}
