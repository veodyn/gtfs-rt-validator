import java.util.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

/**
 * Print the iteration order of a HashMap and a HashSet built by inserting the
 * given keys in the given order. One case per input line: the keys, tab
 * separated. Output is one line per case, keys tab separated, in iteration
 * order, prefixed by "MAP" or "SET".
 *
 * This is the oracle for appendix A of the rule-semantics reference, which
 * proposes simulating HashMap order by sorting on (bucketIndexAtFinalCapacity,
 * insertionIndex) and flags treeification as untested.
 */
public class DumpHashOrder {
    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintWriter out = new PrintWriter(
            new OutputStreamWriter(System.out, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            if (line.isEmpty()) continue;
            String[] keys = line.split("\t", -1);
            Map<String, String> map = new HashMap<>();
            Set<String> set = new HashSet<>();
            for (String k : keys) { map.put(k, "v"); set.add(k); }
            out.println("MAP\t" + String.join("\t", map.keySet()));
            out.println("SET\t" + String.join("\t", set));
        }
        out.flush();
    }
}
