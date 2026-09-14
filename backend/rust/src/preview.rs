//! A frame owns its depth and color storage across all input batches.
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::{shading, visibility_into, MAX_PIXELS};

#[pyclass]
pub struct NativeFrame {
    width: usize,
    height: usize,
    depth: Vec<f64>,
    rgb: Vec<u8>,
    winners: Vec<u32>,
    failed: bool,
}

#[pymethods]
impl NativeFrame {
    #[new]
    pub(crate) fn new(width: usize, height: usize) -> PyResult<Self> {
        let pixels = width
            .checked_mul(height)
            .filter(|&n| n > 0 && n <= MAX_PIXELS)
            .ok_or_else(|| PyValueError::new_err("invalid image dimensions"))?;
        Ok(Self {
            width,
            height,
            depth: vec![f64::INFINITY; pixels],
            rgb: vec![0; pixels * 3],
            winners: vec![u32::MAX; pixels],
            failed: false,
        })
    }

    pub(crate) fn draw_phong(
        &mut self,
        py: Python<'_>,
        triangles: &[u8],
        itemsize: usize,
        normals: &[u8],
        normal_itemsize: usize,
        lighting: [f64; 31],
    ) -> PyResult<usize> {
        self.check()?;
        shading::validate(
            py,
            triangles,
            itemsize,
            normals,
            normal_itemsize,
            self.width,
            self.height,
            &lighting,
        )?;
        let result: Result<usize, &'static str> = py.detach(|| {
            let (_, candidates) = visibility_into(
                triangles,
                itemsize,
                &mut self.depth,
                &mut self.winners,
                self.width,
                self.height,
            )?;
            for (pixel, face) in self.winners.iter().copied().enumerate() {
                if face == u32::MAX {
                    continue;
                }
                let mut record = [0; 24];
                record[..8].copy_from_slice(&(pixel as u64).to_ne_bytes());
                record[8..16].copy_from_slice(&(face as u64).to_ne_bytes());
                shading::shade_into(
                    &record,
                    triangles,
                    itemsize,
                    normals,
                    normal_itemsize,
                    self.width,
                    self.depth.len(),
                    &lighting,
                    &mut self.rgb[pixel * 3..pixel * 3 + 3],
                )?;
            }
            Ok(candidates)
        });
        if result.is_err() {
            self.failed = true;
        }
        result.map_err(PyValueError::new_err)
    }

    pub(crate) fn draw_flat(
        &mut self,
        py: Python<'_>,
        triangles: &[u8],
        itemsize: usize,
        color: [u8; 3],
    ) -> PyResult<usize> {
        self.check()?;
        if ![4, 8].contains(&itemsize) || !triangles.len().is_multiple_of(9 * itemsize) {
            return Err(PyValueError::new_err("invalid triangle buffer"));
        }
        let result: Result<usize, &'static str> = py.detach(|| {
            let (_, candidates) = visibility_into(
                triangles,
                itemsize,
                &mut self.depth,
                &mut self.winners,
                self.width,
                self.height,
            )?;
            for (pixel, face) in self.winners.iter().copied().enumerate() {
                if face != u32::MAX {
                    self.rgb[pixel * 3..pixel * 3 + 3].copy_from_slice(&color);
                }
            }
            Ok(candidates)
        });
        if result.is_err() {
            self.failed = true;
        }
        result.map_err(PyValueError::new_err)
    }

    pub(crate) fn rgba<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        self.check()?;
        PyBytes::new_with(py, self.depth.len() * 4, |out| {
            py.detach(|| {
                for (pixel, rgba) in out.chunks_exact_mut(4).enumerate() {
                    rgba[..3].copy_from_slice(&self.rgb[pixel * 3..pixel * 3 + 3]);
                    rgba[3] = if self.depth[pixel] < f64::INFINITY {
                        255
                    } else {
                        0
                    };
                }
            });
            Ok(())
        })
    }
}

impl NativeFrame {
    fn check(&self) -> PyResult<()> {
        if self.failed {
            Err(PyRuntimeError::new_err("failed frame cannot be published"))
        } else {
            Ok(())
        }
    }
}
