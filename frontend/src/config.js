const API_BASE_URL =
  window.location.hostname === "localhost"
    ? "http://localhost:8000/"
    : "http://reviewanalysis.uxlivinglab.org/api/"; 

export default API_BASE_URL;