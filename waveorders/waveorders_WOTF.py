import numpy as np
import matplotlib.pyplot as plt
from numpy.fft import fft2, ifft2, fftshift, ifftshift


def intensity_mapping(img_stack):
    img_stack_out = np.zeros_like(img_stack)
    img_stack_out[0] = img_stack[0]
    img_stack_out[1] = img_stack[4]
    img_stack_out[2] = img_stack[3]
    img_stack_out[3] = img_stack[1]
    img_stack_out[4] = img_stack[2]
    
    return img_stack_out

def genStarTarget(N, M, blur_px = 2):
    
    '''
    
    generate Siemens star for simulation target
    
    Input:
        (N, M)  : (y, x) dimension of the simulated image
        blur_px : degree of the blurring imposed on the generated image
        
    Output:
        star    : Siemens star with the size of (N, M)
        theta   : polar angle np array with the size of (N, M)
    
    '''
    
    # Construct Siemens star

    x = np.r_[:N]-N//2
    y = np.r_[:M]-M//2

    xx, yy = np.meshgrid(x,y)

    rho = np.sqrt(xx**2 + yy**2)
    theta = np.arctan2(yy, xx)

    star = 1 + np.cos(40*theta)
    star = np.pad(star[10:-10,10:-10],(10,),mode='constant')

    # Filter to prevent aliasing


    Gaussian = np.exp(-rho**2/(2*blur_px**2))

    star = np.maximum(0, np.real(ifft2(fft2(star) * fft2(ifftshift(Gaussian)))))
    star /= np.max(star)
    
    
    return star, theta


def gen_coordinate(img_dim, ps):
    
    '''
    
    generate spatial and spatial frequency coordinate arrays
    
    Input:
        img_dim : describes the (y, x) dimension of the computed 2D space
        ps      : pixel size
        
    Output:
        xx      : 2D x-coordinate array
        yy      : 2D y-coordinate array
        fxx     : 2D spatial frequency array in x-dimension
        fyy     : 2D spatial frequency array in y-dimension
    
    '''
    
    N, M = img_dim
    
    fx = ifftshift((np.r_[:M]-M/2)/M/ps)
    fy = ifftshift((np.r_[:N]-N/2)/N/ps)
    x  = ifftshift((np.r_[:M]-M/2)*ps)
    y  = ifftshift((np.r_[:N]-N/2)*ps)


    xx, yy = np.meshgrid(x, y)
    fxx, fyy = np.meshgrid(fx, fy)

    return (xx, yy, fxx, fyy)



def gen_Pupil(fxx, fyy, NA, lambda_in):
    
    N, M = fxx.shape
    
    Pupil = np.zeros((N,M))
    fr = (fxx**2 + fyy**2)**(1/2)
    Pupil[ fr <= NA/lambda_in] = 1
    
    return Pupil


def gen_Hz_stack(fxx, fyy, Pupil_support, lambda_in, z_stack):
    
    N, M = fxx.shape
    N_stack = len(z_stack)
    N_defocus = len(z_stack)
    
    Hz_stack = np.zeros((N_stack, N, M), complex)
    fr = (fxx**2 + fyy**2)**(1/2)
    
    for i in range(N_stack):
        Hz_stack[i] = Pupil_support * np.exp(1j*2*np.pi/lambda_in*z_stack[i]* ((1 - lambda_in**2 * fr**2) * Pupil_support)**(1/2))

    
    return Hz_stack


def Jones_sample(Ein, t, sa):
    
    Eout = np.zeros_like(Ein)
    Eout[0] = Ein[0] * (t[0]*np.cos(sa)**2 + t[1]*np.sin(sa)**2) + \
              Ein[1] * (t[0] - t[1]) * np.sin(sa) * np.cos(sa)
    Eout[1] = Ein[0] * (t[0] - t[1]) * np.sin(sa) * np.cos(sa) + \
              Ein[1] * (t[0]*np.sin(sa)**2 + t[1]*np.cos(sa)**2)
    
    return Eout


def Jones_to_Stokes(Ein):
    
    _, N, M = Ein.shape
    
    
    Stokes = np.zeros((4, N, M))
    Stokes[0] = np.abs(Ein[0])**2 + np.abs(Ein[1])**2
    Stokes[1] = np.abs(Ein[0])**2 - np.abs(Ein[1])**2
    Stokes[2] = np.real(Ein[0].conj()*Ein[1] + Ein[0]*Ein[1].conj())
    Stokes[3] = np.real(-1j*(Ein[0].conj()*Ein[1] - Ein[0]*Ein[1].conj()))
    
    
    return Stokes


def analyzer_output(Ein, alpha, beta):
    
    Eout = Ein[0] * np.exp(-1j*beta/2) * np.cos(alpha/2) - \
           Ein[1] * 1j * np.exp(1j*beta/2) * np.sin(alpha/2)
    
    return Eout


class waveorders_microscopy:
    
    def __init__(self, img_dim, lambda_illu, ps, NA_obj, NA_illu, z_defocus, chi, LRHC, bg_option):
        
        '''
        
        initialize the system parameters for phase and orders microscopy
        
        Inputs:
            
        
        '''
        
        # Basic parameter 
        self.N, self.M   = img_dim
        self.lambda_illu = lambda_illu
        self.ps          = ps
        self.z_defocus   = z_defocus.copy()
        self.NA_obj      = NA_obj
        self.NA_illu     = NA_illu
        self.N_defocus   = len(z_defocus)
        self.chi         = chi
        self.LRHC        = LRHC
        self.bg_option   = bg_option
        
        # setup microscocpe variables
        self.xx, self.yy, self.fxx, self.fyy = gen_coordinate((self.N, self.M), ps)
        self.Pupil_obj = gen_Pupil(self.fxx, self.fyy, self.NA_obj, self.lambda_illu)
        self.Source = gen_Pupil(self.fxx, self.fyy, self.NA_illu, self.lambda_illu)
        self.Hz_det = gen_Hz_stack(self.fxx, self.fyy, self.Pupil_obj, self.lambda_illu, self.z_defocus)
        self.gen_WOTF()
        self.analyzer_para = np.array([[np.pi/2, np.pi], \
                                       [np.pi/2-self.chi, np.pi], \
                                       [np.pi/2, np.pi-self.chi], \
                                       [np.pi/2+self.chi, np.pi], \
                                       [np.pi/2, np.pi+self.chi]]) # [alpha, beta]
        
        self.N_channel = len(self.analyzer_para)
    
    def gen_WOTF(self):

        self.Hu = np.zeros((self.N_defocus, self.N, self.M),complex)
        self.Hp = np.zeros((self.N_defocus, self.N, self.M),complex)

        for i in range(self.N_defocus):
            H1 = ifft2(fft2(self.Source * self.Hz_det[i]).conj()*fft2(self.Hz_det[i]))
            H2 = ifft2(fft2(self.Source * self.Hz_det[i])*fft2(self.Hz_det[i]).conj())
            I_norm = np.sum(self.Source * self.Hz_det[i] * self.Hz_det[i].conj())
            self.Hu[i] = (H1 + H2)/I_norm
            self.Hp[i] = 1j*(H1-H2)/I_norm
            
    def simulate_waveorders_measurements(self, t_eigen, sa_orientation):        
        
        Stokes_out = np.zeros((self.N_defocus, 4, self.N, self.M))
        I_meas = np.zeros((self.N_defocus, self.N_channel, self.N, self.M))
        
        [idx_y, idx_x] = np.where(self.Source ==1) 
        N_source = len(idx_y)


        for i in range(N_source):
            plane_wave = np.exp(1j*2*np.pi*(self.fyy[idx_y[i], idx_x[i]] * self.yy +\
                                            self.fxx[idx_y[i], idx_x[i]] * self.xx))
            E_field = []
            E_field.append(plane_wave)
            E_field.append(1j*plane_wave) # RHC illumination
            E_field = np.array(E_field)
            
            E_sample = Jones_sample(E_field, t_eigen, sa_orientation)

            for m in range(self.N_defocus):
                
                E_field_out = ifft2(fft2(E_sample) * self.Hz_det[m])
                Stokes_out[m] += Jones_to_Stokes(E_field_out)
                
                for n in range(self.N_channel):
                    I_meas[m,n] += np.abs(analyzer_output(E_field_out, self.analyzer_para[n,0], self.analyzer_para[n,1]))**2
                    
            if np.mod(i+1, 100) == 0 or i+1 == N_source:
                print('Number of sources considered (%d / %d)'%(i+1,N_source))

            
        return I_meas, Stokes_out
    
    
    def Stokes_recon(self, I_meas):
        
        A_forward = 0.5*np.array([[1,0,0,-1], \
                          [1, np.sin(self.chi), 0, -np.cos(self.chi)], \
                          [1, 0, np.sin(self.chi), -np.cos(self.chi)], \
                          [1, -np.sin(self.chi), 0, -np.cos(self.chi)], \
                          [1, 0, -np.sin(self.chi), -np.cos(self.chi)]])
        
        A_pinv = np.linalg.pinv(A_forward)
        
        
        if self.N_defocus == 1:
            S_image_recon = (A_pinv.dot(I_meas.reshape((5, self.N*self.M)))).reshape((4, self.N, self.M))
        else:
            S_image_recon = np.zeros((self.N_defocus, 4, self.N, self.M))
            for i in range(self.N_defocus):
                S_image_recon[i] = (A_pinv.dot(I_meas[i].reshape((5, self.N*self.M)))).reshape((4, self.N, self.M))
            
            
        return S_image_recon
    
    
    def Stokes_transform(self, S_image_recon):
        
        
        if self.N_defocus == 1:
            S_transformed = np.zeros((5, self.N, self.M))
            S_transformed[0] = S_image_recon[0]
            S_transformed[1] = S_image_recon[1] / S_image_recon[3]
            S_transformed[2] = S_image_recon[2] / S_image_recon[3]
            S_transformed[3] = S_image_recon[3]
            S_transformed[4] = (S_image_recon[1]**2 + S_image_recon[2]**2 + S_image_recon[3]**2)**(1/2) / S_image_recon[0] # DoP
        else:
            S_transformed = np.zeros((self.N_defocus, 5, self.N, self.M))
            S_transformed[:,0] = S_image_recon[:,0]
            S_transformed[:,1] = S_image_recon[:,1] / S_image_recon[:,3]
            S_transformed[:,2] = S_image_recon[:,2] / S_image_recon[:,3]
            S_transformed[:,3] = S_image_recon[:,3]
            S_transformed[:,4] = (S_image_recon[:,1]**2 + S_image_recon[:,2]**2 + S_image_recon[:,3]**2)**(1/2) / S_image_recon[:,0] # DoP
            
        return S_transformed
    
    
    def Polscope_bg_correction(self, S_image_tm, S_bg_tm):
        
        if self.N_defocus == 1:
            S_image_tm[0] /= S_bg_tm[0]
            S_image_tm[1] -= S_bg_tm[1]
            S_image_tm[2] -= S_bg_tm[2]
            S_image_tm[4] /= S_bg_tm[4]
        else:
            S_image_tm[:,0] /= S_bg_tm[:,0]
            S_image_tm[:,1] -= S_bg_tm[:,1]
            S_image_tm[:,2] -= S_bg_tm[:,2]
            S_image_tm[:,4] /= S_bg_tm[:,4]
        
        return S_image_tm
    
    
    def Polarization_recon(self, S_image_recon):
        
        if self.N_defocus == 1:
            Recon_para = np.zeros((4, self.N, self.M))
            Recon_para[0] = np.arctan2((S_image_recon[1]**2 + S_image_recon[2]**2)**(1/2) * S_image_recon[3], S_image_recon[3])  # retardance
            if self.LRHC == 'LHC':
                Recon_para[1] = 0.5*np.arctan2(-S_image_recon[1], -S_image_recon[2])%np.pi # slow-axis
            else:
                Recon_para[1] = 0.5*np.arctan2(-S_image_recon[1], S_image_recon[2])%np.pi # slow-axis
            Recon_para[2] = S_image_recon[0] # transmittance
            Recon_para[3] = S_image_recon[4] # DoP

        else:
        
            Recon_para = np.zeros((self.N_defocus, 4, self.N, self.M))
            for i in range(self.N_defocus):
                Recon_para[i,0] = np.arctan2((S_image_recon[i,1]**2 + S_image_recon[i,2]**2)**(1/2) * S_image_recon[i,3], S_image_recon[i,3])  # retardance
                if self.LRHC == 'LHC':
                    Recon_para[i,1] = 0.5*np.arctan2(-S_image_recon[i,1], -S_image_recon[i,2])%np.pi # slow-axis
                else:
                    Recon_para[i,1] = 0.5*np.arctan2(-S_image_recon[i,1], S_image_recon[i,2])%np.pi # slow-axis
                Recon_para[i,2] = S_image_recon[i,0] # transmittance
                Recon_para[i,3] = S_image_recon[i,4] # DoP

        
        return Recon_para
    
    def Phase_recon(self, S0_stack, reg):
        
        for i in range(self.N_defocus):
            S0_stack[i] /= S0_stack[i].mean()
            S0_stack[i] -= 1
            
        
        # Construct AHA matrix

        AHA = [np.sum(np.abs(self.Hu)**2, axis=0) + reg, np.sum(np.conj(self.Hu)*self.Hp, axis=0),\
               np.sum(np.conj(self.Hp)*self.Hu, axis=0), np.sum(np.abs(self.Hp)**2, axis=0) + reg]

        S0_stack_f = fft2(S0_stack)
        b_vec = [np.sum(np.conj(self.Hu)*S0_stack_f, axis=0), \
                 np.sum(np.conj(self.Hp)*S0_stack_f, axis=0)]

        determinant = AHA[0]*AHA[3] - AHA[1]*AHA[2]

        mu_sample = np.real(ifft2((b_vec[0]*AHA[3] - b_vec[1]*AHA[1]) / determinant))
        phi_sample = np.real(ifft2((b_vec[1]*AHA[0] - b_vec[0]*AHA[2]) / determinant))
        
        return mu_sample, phi_sample