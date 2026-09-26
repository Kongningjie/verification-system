import axios from 'axios'

export interface HealthResponse {
  status: 'ok'
  service: string
  environment: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await axios.get<HealthResponse>('/api/v1/health')
  return response.data
}
