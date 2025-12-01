import CoverImageSrc from '../assets/images/image-1.png'

const CoverImage = () => {
    return (
        <div className='my-10 flex justify-center items-center'>
            <img src={CoverImageSrc} alt="cover image" className='responsive-image' />
        </div>

    );
};

export default CoverImage;