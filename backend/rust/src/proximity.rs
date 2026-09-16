//! Immutable bounded closest-surface queries, detached from Python.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

type Point = [f64; 3];
type Triangle = [Point; 3];
const MAX_TRIANGLES: usize = 2_000_000;
const MAX_WORK: usize = 32_000_000;

fn sub(a: Point, b: Point) -> Point {
    std::array::from_fn(|i| a[i] - b[i])
}
fn dot(a: Point, b: Point) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
fn cross(a: Point, b: Point) -> Point {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn point(bytes: &[u8]) -> Point {
    std::array::from_fn(|i| f64::from_ne_bytes(bytes[i * 8..i * 8 + 8].try_into().unwrap()))
}

struct Node {
    low: Point,
    high: Point,
    start: usize,
    end: usize,
    children: Option<(usize, usize)>,
}
impl Node {
    fn distance(&self, p: Point) -> f64 {
        let delta = std::array::from_fn(|i| (self.low[i] - p[i]).max(p[i] - self.high[i]).max(0.0));
        dot(delta, delta)
    }
}

#[pyclass(frozen)]
pub struct SurfaceTree {
    triangles: Vec<Triangle>,
    order: Vec<usize>,
    nodes: Vec<Node>,
}

impl SurfaceTree {
    fn build(bytes: &[u8]) -> Result<Self, &'static str> {
        if bytes.is_empty() || bytes.len() % 72 != 0 || bytes.len() / 72 > MAX_TRIANGLES {
            return Err("invalid_proximity_surface");
        }
        let mut triangles = Vec::with_capacity(bytes.len() / 72);
        for chunk in bytes.chunks_exact(72) {
            let triangle = [
                point(&chunk[..24]),
                point(&chunk[24..48]),
                point(&chunk[48..]),
            ];
            if !triangle.iter().flatten().all(|v| v.is_finite()) {
                return Err("invalid_proximity_surface");
            }
            let normal = cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]));
            let area = dot(normal, normal);
            if !area.is_finite() || area <= 0.0 {
                return Err("invalid_proximity_surface");
            }
            triangles.push(triangle);
        }
        let bounds: Vec<(Point, Point)> = triangles
            .iter()
            .map(|t| {
                (
                    std::array::from_fn(|i| t[0][i].min(t[1][i]).min(t[2][i])),
                    std::array::from_fn(|i| t[0][i].max(t[1][i]).max(t[2][i])),
                )
            })
            .collect();
        let centers: Vec<Point> = bounds
            .iter()
            .map(|(lo, hi)| std::array::from_fn(|i| (lo[i] + hi[i]) / 2.0))
            .collect();
        if !centers.iter().flatten().all(|value| value.is_finite()) {
            return Err("invalid_proximity_surface");
        }
        let count = triangles.len();
        let mut tree = Self {
            triangles,
            order: (0..count).collect(),
            nodes: Vec::new(),
        };
        tree.branch(0, count, &bounds, &centers);
        Ok(tree)
    }

    fn branch(
        &mut self,
        start: usize,
        end: usize,
        bounds: &[(Point, Point)],
        centers: &[Point],
    ) -> usize {
        let mut low = [f64::INFINITY; 3];
        let mut high = [f64::NEG_INFINITY; 3];
        let mut center_low = low;
        let mut center_high = high;
        for &id in &self.order[start..end] {
            for axis in 0..3 {
                low[axis] = low[axis].min(bounds[id].0[axis]);
                high[axis] = high[axis].max(bounds[id].1[axis]);
                center_low[axis] = center_low[axis].min(centers[id][axis]);
                center_high[axis] = center_high[axis].max(centers[id][axis]);
            }
        }
        let id = self.nodes.len();
        self.nodes.push(Node {
            low,
            high,
            start,
            end,
            children: None,
        });
        if end - start > 32 {
            let mut axis = 0;
            for candidate in 1..3 {
                if center_high[candidate] - center_low[candidate]
                    > center_high[axis] - center_low[axis]
                {
                    axis = candidate;
                }
            }
            self.order[start..end].sort_by(|&a, &b| centers[a][axis].total_cmp(&centers[b][axis]));
            let middle = start + (end - start) / 2;
            let left = self.branch(start, middle, bounds, centers);
            let right = self.branch(middle, end, bounds, centers);
            self.nodes[id].children = Some((left, right));
        }
        id
    }

    fn query(&self, bytes: &[u8], max_work: usize) -> Result<Vec<u8>, &'static str> {
        if bytes.is_empty() || bytes.len() % 24 != 0 || bytes.len() / 24 > 5000 {
            return Err("invalid_proximity_points");
        }
        if max_work == 0 || max_work > MAX_WORK {
            return Err("invalid_proximity_budget");
        }
        let mut output = Vec::with_capacity(bytes.len() / 24 * 32);
        let mut work = 0usize;
        for chunk in bytes.chunks_exact(24) {
            let p = point(chunk);
            if !p.iter().all(|v| v.is_finite()) {
                return Err("invalid_proximity_points");
            }
            let mut best = f64::INFINITY;
            let mut nearest = [0.0; 3];
            let mut stack = vec![(0, false)];
            if self.nodes[0].children.is_some() {
                stack.push((0, true));
            }
            while let Some((id, seed)) = stack.pop() {
                let node = &self.nodes[id];
                if node.distance(p) > best + 1e-20 {
                    continue;
                }
                if let Some((left, right)) = node.children {
                    if seed {
                        stack.push((
                            if self.nodes[left].distance(p) <= self.nodes[right].distance(p) {
                                left
                            } else {
                                right
                            },
                            true,
                        ));
                    } else {
                        stack.push((right, false));
                        stack.push((left, false));
                    }
                } else {
                    work += node.end - node.start;
                    if work > max_work {
                        return Err("proximity_work_limit");
                    }
                    for &index in &self.order[node.start..node.end] {
                        let (distance, closest) = triangle_closest(p, self.triangles[index]);
                        if distance < best {
                            best = distance;
                            nearest = closest;
                        }
                    }
                }
            }
            if !best.is_finite() {
                return Err("invalid_proximity_points");
            }
            for value in [best.sqrt(), nearest[0], nearest[1], nearest[2]] {
                output.extend_from_slice(&value.to_ne_bytes());
            }
        }
        Ok(output)
    }
}

fn triangle_closest(p: Point, [a, b, c]: Triangle) -> (f64, Point) {
    let ab = sub(b, a);
    let ac = sub(c, a);
    let normal = cross(ab, ac);
    let square = dot(normal, normal);
    let height = dot(sub(p, a), normal) / square;
    let projected = std::array::from_fn(|i| p[i] - height * normal[i]);
    let ap = sub(projected, a);
    let d00 = dot(ab, ab);
    let d01 = dot(ab, ac);
    let d11 = dot(ac, ac);
    let d20 = dot(ap, ab);
    let d21 = dot(ap, ac);
    let v = (d11 * d20 - d01 * d21) / square;
    let w = (d00 * d21 - d01 * d20) / square;
    let mut distance = if v >= 0.0 && w >= 0.0 && v + w <= 1.0 {
        height * height * square
    } else {
        f64::INFINITY
    };
    let mut chosen = projected;
    for (first, second) in [(a, b), (b, c), (c, a)] {
        let edge = sub(second, first);
        let parameter = (dot(sub(p, first), edge) / dot(edge, edge)).clamp(0.0, 1.0);
        let closest = std::array::from_fn(|i| first[i] + parameter * edge[i]);
        let delta = sub(p, closest);
        let squared = dot(delta, delta);
        if squared < distance {
            distance = squared;
            chosen = closest;
        }
    }
    (distance, chosen)
}

#[pymethods]
impl SurfaceTree {
    #[new]
    fn new(py: Python<'_>, triangles: &[u8]) -> PyResult<Self> {
        py.detach(|| Self::build(triangles))
            .map_err(PyValueError::new_err)
    }

    fn closest<'py>(
        &self,
        py: Python<'py>,
        points: &[u8],
        max_work: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let output = py
            .detach(|| self.query(points, max_work))
            .map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &output))
    }
}
