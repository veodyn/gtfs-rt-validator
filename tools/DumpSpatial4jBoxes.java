/*
 * Oracle for src/gtfs_rt_validator/geometry/bbox.py.
 *
 * Reproduces exactly what GtfsMetadata does to build E028's bounding boxes:
 *
 *     ShapeFactory sf = JtsSpatialContext.GEO.getShapeFactory();
 *     ShapeFactory.MultiPointBuilder b = sf.multiPoint();
 *     ... b.pointXY(lon, lat) ...
 *     Rectangle box = b.build().getBoundingBox();
 *     Rectangle buffered = box.getBuffered(d, box.getContext()).getBoundingBox();
 *
 * and what GtfsUtils.isPositionWithinShape does to query them:
 *
 *     Point p = SpatialContext.GEO.getShapeFactory().pointXY(lon, lat);
 *     boolean inside = bounds.relate(p).equals(SpatialRelation.CONTAINS);
 *
 * Note the two contexts: the boxes are built in the JTS geo context, the query
 * point in the plain geo one. Upstream does that too. It does not change any
 * answer, since RectangleImpl.relate(Point) reads only the point's x and y, but
 * it is reproduced rather than tidied so a later reader can check.
 *
 * spatial4j 0.6 needs com.vividsolutions:jts:1.13 beside it. RectangleImpl and
 * DistanceUtils alone would not, but JtsSpatialContext.GEO is what upstream uses
 * to build the multipoint, and that class links against JTS. Both jars live in
 * tools/.jars/, which is gitignored, as gen_schema_2015.py's two do.
 *
 * Run (built-in corpus, a corpus file, or stdin):
 *   J=tools/.jars; CP=$J/spatial4j-0.6.jar:$J/jts-1.13.jar
 *   java -cp $CP tools/DumpSpatial4jBoxes.java
 *   java -cp $CP tools/DumpSpatial4jBoxes.java corpus.txt
 *   java -cp $CP tools/DumpSpatial4jBoxes.java - < corpus.txt
 *
 * Corpus grammar. Directives are separated by newlines or semicolons, '#' starts
 * a comment that runs to end of line, and blanks are ignored:
 *   case <name>        start a case
 *   point <lon> <lat>  add a point to the multipoint, in builder order
 *   buffer <degrees>   the buffer distance for this case
 *   test <lon> <lat>   a containment query, asked of both boxes
 *   end                finish the case
 *
 * Output: one flat line per case, fields separated by spaces, sub-fields by
 * commas and repeats by '|'. Doubles go through Double.toString, which
 * round-trips through Python's float():
 *
 *   <name> buffer=<d> points=<lon>,<lat>|... raw=<minX>,<maxX>,<minY>,<maxY>
 *          buffered=<minX>,<maxX>,<minY>,<maxY> tests=<lon>,<lat>,<in raw>,<in buffered>|...
 *
 * all on one line, or on failure:
 *
 *   <name> error=<exception class>:<message>
 *
 * One line per case rather than one per record because tests/test_bbox.py
 * embeds this output verbatim as its expectations, and the repo caps a file at
 * 300 lines.
 */

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import org.locationtech.spatial4j.context.SpatialContext;
import org.locationtech.spatial4j.context.jts.JtsSpatialContext;
import org.locationtech.spatial4j.shape.Point;
import org.locationtech.spatial4j.shape.Rectangle;
import org.locationtech.spatial4j.shape.Shape;
import org.locationtech.spatial4j.shape.ShapeFactory;
import org.locationtech.spatial4j.shape.SpatialRelation;

public class DumpSpatial4jBoxes {

  /*
   * The default corpus, kept in the source so a bare run is repeatable with no
   * companion script. tools/diff_geometry_against_java.py now drives this
   * oracle as well as the JTS one, feeding it a much larger generated corpus;
   * what is spelled out below is the fallback a bare run uses.
   *
   * 0.014470064717285165 is REGION_BUFFER_DEGREES, GtfsMetadata.java:122, and
   * 0.001798640735523327 is TRIP_BUFFER_DEGREES, line 45. Both are spelled out
   * rather than computed so the corpus stays a flat text artifact.
   */
  static final String BUILT_IN_CORPUS = """
      # the worked case: a Tampa-sized box at 28 N
      case midlat; point -82.5 27.95; point -82.4 28.05; buffer 0.014470064717285165
      test -82.45 28.0; test -82.5 27.95; test -82.51639597602060 27.95
      test -82.6 28.0; test -82.4 28.064470064717288; test -82.4 28.07; end

      # the equator, where the longitude correction is at its smallest
      case equator; point 0.0 0.0; point 0.1 0.05; buffer 0.014470064717285165
      test 0.05 0.0; test -0.0144 0.0; test -0.0145 0.0; end

      # high latitude: cos(lat) is small, so the longitude buffer is much wider
      case highlat; point 18.0 69.6; point 18.2 69.7; buffer 0.014470064717285165
      test 18.1 69.65; test 17.95 69.65; test 17.9 69.65; end

      # extreme latitude, still short of the pole trigger
      case extremelat; point 0.0 89.9; point 1.0 89.98; buffer 0.014470064717285165
      test 0.5 89.95; test 179.0 89.95; test 0.5 89.5; end

      # north pole: maxY + distance >= 90 takes the world-wrap branch
      case northpole; point 10.0 89.99; point -170.0 89.995
      buffer 0.014470064717285165
      test 0.0 89.999; test 179.9 89.99; test 0.0 89.9; test 0.0 89.97; end

      # south pole: minY - distance <= -90 takes the other world-wrap branch
      case southpole; point 10.0 -89.99; point -170.0 -89.995
      buffer 0.014470064717285165
      test 0.0 -89.999; test 179.9 -89.99; test 0.0 -89.9; test 0.0 -89.97; end

      # the antimeridian: the multipoint bbox picks the biggest longitude gap
      case antimeridian; point 179.9 -16.5; point -179.9 -16.6
      buffer 0.014470064717285165
      test 180.0 -16.55; test -180.0 -16.55; test 179.95 -16.55
      test -179.95 -16.55; test 0.0 -16.55; test 179.88 -16.55
      test 179.87 -16.55; end

      # three points straddling 180, but the biggest gap is on the other side
      case gapelsewhere; point 179.9 -16.5; point -179.9 -16.6; point 10.0 -16.55
      buffer 0.014470064717285165
      test 100.0 -16.55; test -100.0 -16.55; test 0.0 -16.55; end

      # a single point: a zero-area box
      case singlepoint; point -122.4 37.8; buffer 0.014470064717285165
      test -122.4 37.8; test -122.4 37.814470064717285; test -122.4 37.82; end

      # duplicate points collapse to the same zero-area box
      case duplicatepoints; point 5.0 45.0; point 5.0 45.0; point 5.0 45.0
      buffer 0.014470064717285165; test 5.0 45.0; test 5.02 45.0; end

      # the degenerate case: no stop had both coordinates, so no points at all
      case degenerate; buffer 0.014470064717285165
      test 0.0 0.0; test -82.45 28.0; test 180.0 90.0; end

      # a box wide enough that the buffer itself wraps the world in longitude
      case worldwrapbybuffer; point -179.999 10.0; point 179.999 10.1
      point 0.0 10.05; buffer 0.014470064717285165
      test 90.0 10.05; test -90.0 10.05; test 90.0 10.2; end

      # a box already touching both dateline edges
      case fullwidth; point -180.0 -5.0; point 180.0 5.0; point 0.0 0.0
      buffer 0.014470064717285165
      test 123.0 0.0; test -123.0 5.0; test 0.0 5.02; end

      # a zero buffer: calcBoxByDistFromPt_deltaLonDEG short-circuits to 0
      case zerobuffer; point -1.0 51.5; point 1.0 51.6; buffer 0.0
      test 0.0 51.55; test -1.0 51.5; test -1.0001 51.5; end

      # the trip buffer distance, on a box near the equator
      case tripbuffer; point -78.5 -0.2; point -78.4 0.1; buffer 0.001798640735523327
      test -78.45 0.0; test -78.502 0.0; end

      # points spread over more than 180 degrees but not across the dateline
      case widenowrap; point -100.0 20.0; point 100.0 30.0; point 0.0 25.0
      buffer 0.014470064717285165
      test 0.0 25.0; test 150.0 25.0; test -150.0 25.0; end
      """;

  static final class Case {
    String name;
    final List<double[]> points = new ArrayList<>();
    final List<double[]> tests = new ArrayList<>();
    double buffer = Double.NaN;
  }

  public static void main(String[] args) throws IOException {
    for (Case c : parse(readCorpus(args))) {
      run(c);
    }
  }

  static String readCorpus(String[] args) throws IOException {
    if (args.length == 0) {
      return BUILT_IN_CORPUS;
    }
    if (!args[0].equals("-")) {
      return Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);
    }
    StringBuilder sb = new StringBuilder();
    try (BufferedReader r =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
      String line;
      while ((line = r.readLine()) != null) {
        sb.append(line).append('\n');
      }
    }
    return sb.toString();
  }

  static List<Case> parse(String text) {
    List<Case> cases = new ArrayList<>();
    Case current = null;
    for (String rawLine : text.split("\n", -1)) {
      String stripped = rawLine.split("#", 2)[0];
      for (String directive : stripped.split(";")) {
        String line = directive.trim();
        if (line.isEmpty()) {
          continue;
        }
        String[] p = line.split("\\s+");
        if (p[0].equals("case")) {
          current = new Case();
          current.name = p[1];
        } else if (p[0].equals("point")) {
          current.points.add(new double[] {Double.parseDouble(p[1]), Double.parseDouble(p[2])});
        } else if (p[0].equals("test")) {
          current.tests.add(new double[] {Double.parseDouble(p[1]), Double.parseDouble(p[2])});
        } else if (p[0].equals("buffer")) {
          current.buffer = Double.parseDouble(p[1]);
        } else if (p[0].equals("end")) {
          cases.add(current);
          current = null;
        } else {
          throw new IllegalArgumentException("unknown directive: " + line);
        }
      }
    }
    if (current != null) {
      throw new IllegalArgumentException("corpus ended inside case " + current.name);
    }
    return cases;
  }

  static void run(Case c) {
    StringBuilder out = new StringBuilder(c.name);
    out.append(" buffer=").append(Double.toString(c.buffer)).append(" points=");
    for (int i = 0; i < c.points.size(); i++) {
      out.append(i == 0 ? "" : "|").append(pair(c.points.get(i)));
    }
    Rectangle raw;
    Rectangle buffered;
    try {
      ShapeFactory sf = JtsSpatialContext.GEO.getShapeFactory();
      ShapeFactory.MultiPointBuilder builder = sf.multiPoint();
      for (double[] p : c.points) {
        builder.pointXY(p[0], p[1]);
      }
      raw = builder.build().getBoundingBox();
      buffered = raw.getBuffered(c.buffer, raw.getContext()).getBoundingBox();
    } catch (RuntimeException e) {
      System.out.println(out + " error=" + e.getClass().getName() + ":" + e.getMessage());
      return;
    }
    out.append(" raw=").append(box(raw)).append(" buffered=").append(box(buffered));
    out.append(" tests=");
    for (int i = 0; i < c.tests.size(); i++) {
      double[] t = c.tests.get(i);
      out.append(i == 0 ? "" : "|").append(pair(t))
          .append(',').append(contains(raw, t[0], t[1]))
          .append(',').append(contains(buffered, t[0], t[1]));
    }
    System.out.println(out);
  }

  static String pair(double[] p) {
    return Double.toString(p[0]) + "," + Double.toString(p[1]);
  }

  static String box(Rectangle r) {
    return Double.toString(r.getMinX()) + "," + Double.toString(r.getMaxX()) + ","
        + Double.toString(r.getMinY()) + "," + Double.toString(r.getMaxY());
  }

  static boolean contains(Rectangle bounds, double lon, double lat) {
    // GtfsUtils.isPositionWithinShape, verbatim. `bounds` is typed Shape there,
    // so relate(Shape) runs, and its isEmpty() guard is what makes the NaN box
    // answer DISJOINT to every point instead of throwing.
    Shape asShape = bounds;
    Point p = SpatialContext.GEO.getShapeFactory().pointXY(lon, lat);
    return asShape.relate(p).equals(SpatialRelation.CONTAINS);
  }
}
