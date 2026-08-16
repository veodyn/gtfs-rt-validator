/*
 * Oracle for src/gtfs_rt_validator/geometry/buffer.py.
 *
 * Answers the one question E029 asks: is a point inside the planar buffer that
 * com.vividsolutions:jts:1.13 computes around a trip shape? Upstream's
 * GtfsMetadata.getBufferedTripShape is a one-line delegation to
 * JtsGeometry.getBuffered, which is itself a one-line delegation to
 * Geometry.buffer(TRIP_BUFFER_DEGREES) on a LineString built from shape points
 * in raw lon/lat degrees. The containment test then reduces to
 * `geom.disjoint(point) ? DISJOINT : CONTAINS`, by way of
 * GtfsUtils.isPositionWithinShape and JtsGeometry.relate(Point).
 * So this dumper calls buffer() and disjoint() directly: spatial4j is not on the
 * classpath because nothing on that path changes the answer.
 *
 * Buffering in degrees on a planar geometry is why E029's buffer is about 200
 * metres north to south but only 200*cos(lat) east to west, while the occurrence
 * text it writes still says 200. That is upstream's behaviour, not a defect to
 * correct here: this file exists to reproduce it, not to fix it.
 *
 * The groupId matters. org.locationtech.jts is a different artifact with
 * different behaviour; upstream's pom.xml pins com.vividsolutions:jts:1.13 and
 * that is what this must be run against.
 *
 * Driven by tools/diff_geometry_against_java.py, which fetches the jar. By hand:
 *   java -cp tools/.jars/jts-1.13.jar tools/DumpJtsBuffer.java < cases.tsv
 *
 * Input, one case per line, tab separated:
 *   <id>  <lon,lat;lon,lat;...>  <lon>  <lat>  <distance>
 * Output, one line per case:
 *   <id>  CONTAINS|DISJOINT                    (default)
 *   <id>  POLY  <x> <y> <x> <y> ...            (--poly, one line per ring, and
 *   <id>  HOLE  <x> <y> <x> <y> ...             every line carries the id: a
 *                                               self-crossing shape really does
 *                                               buffer to a polygon with a hole,
 *                                               and both rings are boundary)
 *   <id>  CURVE <x> <y> <x> <y> ...            (--curve, the raw offset curve
 *                                               before noding, straight out of
 *                                               OffsetCurveBuilder)
 *   <id>  ERROR <java exception>
 *
 * --poly and --curve exist so a failing containment case can be inspected by
 * hand: --curve is what buffer.py reproduces vertex for vertex, --poly is what
 * JTS makes of it after noding and overlay.
 */

import com.vividsolutions.jts.geom.Coordinate;
import com.vividsolutions.jts.geom.Geometry;
import com.vividsolutions.jts.geom.GeometryFactory;
import com.vividsolutions.jts.geom.LineString;
import com.vividsolutions.jts.geom.Point;
import com.vividsolutions.jts.geom.Polygon;
import com.vividsolutions.jts.geom.PrecisionModel;
import com.vividsolutions.jts.operation.buffer.BufferParameters;
import com.vividsolutions.jts.operation.buffer.OffsetCurveBuilder;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class DumpJtsBuffer {

  private static final GeometryFactory GF = new GeometryFactory();

  public static void main(String[] args) throws Exception {
    String mode = args.length > 0 ? args[0] : "--contains";
    if (args.length > 0 && args[0].equals("--params")) {
      dumpParams();
      return;
    }
    BufferedReader in = new BufferedReader(new InputStreamReader(System.in, "UTF-8"));
    String line;
    while ((line = in.readLine()) != null) {
      if (line.trim().isEmpty()) {
        continue;
      }
      String[] f = line.split("\t", -1);
      String id = f[0];
      try {
        Coordinate[] coords = parseShape(f[1]);
        double lon = Double.parseDouble(f[2]);
        double lat = Double.parseDouble(f[3]);
        double dist = Double.parseDouble(f[4]);
        if (mode.equals("--curve")) {
          System.out.println(id + "\tCURVE" + curve(coords, dist));
        } else if (mode.equals("--poly")) {
          for (String ring : polygonRings(coords, dist)) {
            System.out.println(id + "\t" + ring);
          }
        } else {
          System.out.println(id + "\t" + (contains(coords, lon, lat, dist) ? "CONTAINS" : "DISJOINT"));
        }
      } catch (Exception e) {
        System.out.println(id + "\tERROR\t" + e.getClass().getName() + ": " + e.getMessage());
      }
    }
  }

  /** The BufferParameters defaults buffer.py assumes, printed rather than trusted. */
  private static void dumpParams() {
    BufferParameters bp = new BufferParameters();
    System.out.println("quadrantSegments\t" + bp.getQuadrantSegments());
    System.out.println("endCapStyle\t" + bp.getEndCapStyle());
    System.out.println("joinStyle\t" + bp.getJoinStyle());
    System.out.println("mitreLimit\t" + bp.getMitreLimit());
    // No getSimplifyFactor() in 1.13: the simplification tolerance is
    // OffsetCurveBuilder's own private SIMPLIFY_FACTOR = 100.0, so distTol is
    // distance / 100. It moved onto BufferParameters only in later versions.
    System.out.println("isSingleSided\t" + bp.isSingleSided());
    System.out.println("CAP_ROUND\t" + BufferParameters.CAP_ROUND);
    System.out.println("JOIN_ROUND\t" + BufferParameters.JOIN_ROUND);
  }

  private static boolean contains(Coordinate[] coords, double lon, double lat, double dist) {
    LineString shape = GF.createLineString(coords);
    Geometry buffered = shape.buffer(dist);
    Point p = GF.createPoint(new Coordinate(lon, lat));
    // GtfsUtils.isPositionWithinShape -> JtsGeometry.relate(Point) -> this.
    return !buffered.disjoint(p);
  }

  /**
   * Every ring of the buffer, shell and hole alike, one per returned string.
   *
   * They are returned rather than concatenated because the caller has to print
   * the case id on each line. An earlier version wrote the hole ring on a bare
   * "\nHOLE" line with no id, so the Python harness filed it under the literal
   * key "HOLE" and never probed it; the same bug hid the second and later
   * shells of a MultiPolygon, which were appended with no separator at all.
   */
  private static List<String> polygonRings(Coordinate[] coords, double dist) {
    Geometry buffered = GF.createLineString(coords).buffer(dist);
    List<String> rings = new ArrayList<>();
    if (buffered.isEmpty()) {
      rings.add("POLY\tEMPTY");
      return rings;
    }
    for (int g = 0; g < buffered.getNumGeometries(); g++) {
      Polygon poly = (Polygon) buffered.getGeometryN(g);
      rings.add("POLY" + coordinates(poly.getExteriorRing().getCoordinates()));
      for (int h = 0; h < poly.getNumInteriorRing(); h++) {
        rings.add("HOLE" + coordinates(poly.getInteriorRingN(h).getCoordinates()));
      }
    }
    return rings;
  }

  /**
   * The raw offset curve, before noding and overlay. This is the exact artefact
   * buffer.py reproduces, so a mismatch here localises a bug to the curve
   * generator rather than to the containment rule.
   */
  private static String curve(Coordinate[] coords, double dist) {
    // Same construction BufferOp uses for a floating precision model: see
    // BufferOp.bufferOriginalPrecision -> BufferBuilder.buffer.
    OffsetCurveBuilder ocb = new OffsetCurveBuilder(new PrecisionModel(), new BufferParameters());
    Coordinate[] clean = com.vividsolutions.jts.geom.CoordinateArrays.removeRepeatedPoints(coords);
    Coordinate[] raw = ocb.getLineCurve(clean, dist);
    return raw == null ? "\tNULL" : coordinates(raw);
  }

  private static String coordinates(Coordinate[] pts) {
    StringBuilder sb = new StringBuilder();
    for (Coordinate p : pts) {
      // Double.toString round-trips, so the Python side reads back the exact bits.
      sb.append('\t').append(Double.toString(p.x)).append(' ').append(Double.toString(p.y));
    }
    return sb.toString();
  }

  private static Coordinate[] parseShape(String text) {
    if (text.isEmpty()) {
      return new Coordinate[0];
    }
    String[] parts = text.split(";");
    Coordinate[] coords = new Coordinate[parts.length];
    for (int i = 0; i < parts.length; i++) {
      String[] xy = parts[i].split(",");
      coords[i] = new Coordinate(Double.parseDouble(xy[0]), Double.parseDouble(xy[1]));
    }
    return coords;
  }
}
